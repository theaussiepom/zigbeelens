from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from zigbeelens import __version__
from zigbeelens.api.auth import (
    BearerPreflightRoute,
    require_mutation_access,
    require_read_access,
)
from zigbeelens.api.summary import capabilities_dict, service_status_dict
from zigbeelens.app.context import AppContext, get_context
from zigbeelens.config.redaction import redact_mqtt_server
from zigbeelens.config.security_status import build_security_config_status
from zigbeelens.enrichment.ha import (
    apply_ha_enrichment,
    clear_ha_enrichment,
    enrichment_status_dict,
)
from zigbeelens.mqtt.lifecycle import collector_status_dict
from zigbeelens.mqtt_discovery import discovery_status_dict
from zigbeelens.topology.service import get_topology_service, topology_status_dict
from zigbeelens.topology.topics import CAPTURE_WARNING
from zigbeelens.schemas import (
    DashboardPayload,
    DeviceDetail,
    HealthResponse,
    PaginatedResponse,
    RedactionOptions,
    RedactionProfile,
    ReportDetail,
    ReportFormat,
    ReportRequest,
    ReportScope,
    ReportSummary,
    TopologyCaptureRequest,
    ZigbeeLensConfigStatus,
)
from zigbeelens.services.report_scope import ReportScopeAmbiguityError
from zigbeelens.services.reports import (
    generate_report,
    report_body_as_json,
    report_body_as_yaml,
    store_report,
    summary_from_detail,
    summary_from_row,
)

public_router = APIRouter()
read_router = APIRouter(
    dependencies=[Depends(require_read_access)],
    route_class=BearerPreflightRoute,
)
mutation_router = APIRouter(
    dependencies=[Depends(require_mutation_access)],
    route_class=BearerPreflightRoute,
)


def ctx_dep() -> AppContext:
    return get_context()


@public_router.get("/version")
def version() -> dict[str, str]:
    return {"version": __version__, "name": "zigbeelens-core"}


@read_router.get("/health", response_model=HealthResponse)
def health(ctx: AppContext = Depends(ctx_dep)) -> HealthResponse:
    db_ok = ctx.db.ping()
    collector = collector_status_dict(ctx)
    return HealthResponse(
        status="ok" if db_ok and ctx.config_loaded else "degraded",
        version=__version__,
        uptime_seconds=ctx.uptime_seconds(),
        config_loaded=ctx.config_loaded,
        mock_mode=ctx.config.mode.mock,
        database="ok" if db_ok else "error",
        migration_version=ctx.migration_version,
        collector=collector,
        mqtt_discovery=discovery_status_dict(ctx),
        topology=topology_status_dict(ctx),
        home_assistant_enrichment=enrichment_status_dict(ctx.repo),
    )


@read_router.get("/capabilities")
def capabilities(ctx: AppContext = Depends(ctx_dep)) -> dict:
    return capabilities_dict(ctx)


@read_router.get("/status")
def status(ctx: AppContext = Depends(ctx_dep)) -> dict:
    return service_status_dict(ctx)


@read_router.get("/config/status", response_model=ZigbeeLensConfigStatus)
def config_status(
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> ZigbeeLensConfigStatus:
    active_scenario = scenario
    if ctx.config.mode.mock and not scenario:
        active_scenario = ctx.config.mode.default_scenario

    collector = collector_status_dict(ctx)
    return ZigbeeLensConfigStatus(
        version=__version__,
        uptime_seconds=ctx.uptime_seconds(),
        mqtt_connected=bool(collector.get("connected")),
        mqtt_server=redact_mqtt_server(ctx.config.mqtt.server, ctx.config.mqtt.username),
        configured_networks=[
            {"id": n.id, "name": n.name, "base_topic": n.base_topic}
            for n in ctx.config.networks
        ],
        storage_path=ctx.config.storage.path,
        storage_ready=ctx.db.path.exists(),
        retention_days=ctx.config.storage.retention_days,
        features=ctx.config.features.model_dump(),
        mqtt_discovery=ctx.config.mqtt_discovery.model_dump(),
        topology=ctx.config.topology.model_dump(),
        diagnostics=ctx.config.diagnostics.model_dump(),
        data_mode="mock" if ctx.config.mode.mock else "live",
        mock_mode=ctx.config.mode.mock,
        active_scenario=active_scenario,
        security=build_security_config_status(ctx.config),
    )


@read_router.get("/scenarios")
def scenarios() -> list[dict[str, str]]:
    from zigbeelens.services.data_service import DataService

    return DataService.list_scenarios()


@read_router.get("/dashboard", response_model=DashboardPayload)
def dashboard(
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> DashboardPayload:
    return ctx.data.dashboard(scenario)


@read_router.get("/networks", response_model=PaginatedResponse)
def networks(
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> PaginatedResponse:
    items = ctx.data.networks(scenario)
    return PaginatedResponse(items=items, total=len(items))


@read_router.get("/networks/{network_id}")
def network_detail(
    network_id: str,
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
):
    net = ctx.data.network(network_id, scenario)
    if not net:
        raise HTTPException(status_code=404, detail="Network not found")
    return net


@read_router.get("/devices", response_model=PaginatedResponse)
def devices(
    scenario: str | None = Query(default=None),
    network_id: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> PaginatedResponse:
    items = ctx.data.devices(scenario, network_id)
    return PaginatedResponse(items=items, total=len(items))


@read_router.get("/devices/{network_id}/{ieee_address}", response_model=DeviceDetail)
def device_detail(
    network_id: str,
    ieee_address: str,
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> DeviceDetail:
    device = ctx.data.device(network_id, ieee_address, scenario)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@read_router.get("/devices/{network_id}/{ieee_address}/story")
def device_story(
    network_id: str,
    ieee_address: str,
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> dict:
    """Read-only deterministic device story from stored evidence or scenario fixtures.

    Returns coded decision output only — no final user-facing prose. Unknown
    devices use the same not-found contract as other device routes.
    """
    story = ctx.data.device_story(network_id, ieee_address, scenario)
    if story is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return story.model_dump(mode="json")


@read_router.get("/devices/{network_id}/{ieee_address}/coverage")
def device_coverage(network_id: str, ieee_address: str, ctx: AppContext = Depends(ctx_dep)) -> list[dict]:
    """Read-only per-device evidence coverage from stored data.

    Returns coded DataCoverage facts only — presenters map labels and copy.
    """
    from zigbeelens.decisions.device_coverage import device_coverage_for_device

    if ctx.repo.get_network(network_id) is None:
        raise HTTPException(status_code=404, detail="Network not found")
    coverage = device_coverage_for_device(ctx.repo, network_id, ieee_address)
    if coverage is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return [item.model_dump(mode="json") for item in coverage]


@read_router.get("/routers", response_model=PaginatedResponse)
def routers(
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> PaginatedResponse:
    items = ctx.data.routers(scenario)
    return PaginatedResponse(items=items, total=len(items))


@read_router.get("/incidents", response_model=PaginatedResponse)
def incidents(
    scenario: str | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    updated_after: str | None = Query(default=None),
    network_id: str | None = Query(default=None),
    device_ieee: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> PaginatedResponse:
    from zigbeelens.storage.incident_collection import (
        IncidentCollectionCursorError,
        IncidentCollectionQueryError,
        build_incident_collection_query,
    )

    try:
        query = build_incident_collection_query(
            status=status,
            updated_after=updated_after,
            network_id=network_id,
            device_ieee=device_ieee,
            limit=limit,
            cursor=cursor,
        )
        page = ctx.data.incidents(scenario, query=query)
    except IncidentCollectionQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IncidentCollectionCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PaginatedResponse(
        items=page["items"],
        total=page["total"],
        limit=page["limit"],
        next_cursor=page["next_cursor"],
    )


@read_router.get("/incidents/{incident_id}")
def incident_detail(
    incident_id: str,
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
):
    inc = ctx.data.incident(incident_id, scenario)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc


@read_router.get("/timeline", response_model=PaginatedResponse)
def timeline(
    scenario: str | None = Query(default=None),
    network_id: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> PaginatedResponse:
    items = ctx.data.timeline(scenario, network_id)
    return PaginatedResponse(items=items, total=len(items))


def _build_request(
    *,
    scope: ReportScope,
    format: ReportFormat,
    profile: RedactionProfile,
    network_id: str | None,
    incident_id: str | None,
    device: str | None,
    preserve_friendly_names: bool | None,
    hash_ieee_addresses: bool | None,
    redact_hostnames: bool | None,
    redact_ip_addresses: bool | None,
    redact_network_names: bool | None,
    include_timeline: bool | None,
    include_raw_payloads: bool | None,
) -> ReportRequest:
    return ReportRequest(
        format=format,
        scope=scope,
        incident_id=incident_id,
        network_id=network_id,
        device=device,
        redaction=RedactionOptions(
            profile=profile,
            preserve_friendly_names=preserve_friendly_names,
            hash_ieee_addresses=hash_ieee_addresses,
            redact_hostnames=redact_hostnames,
            redact_ip_addresses=redact_ip_addresses,
            redact_network_names=redact_network_names,
            include_timeline=include_timeline,
            include_raw_payloads=include_raw_payloads,
        ),
    )


def _sanitize_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return token[:40]


def _report_filename(detail: ReportDetail) -> str:
    timestamp = detail.generated_at[:19].replace(":", "-")
    parts = ["zigbeelens-report"]
    if detail.scope != "full":
        parts.append(_sanitize_token(detail.scope))
        if detail.scope == "device" and detail.devices:
            parts.append(_sanitize_token(detail.devices[0].friendly_name))
        elif detail.networks:
            parts.append(_sanitize_token(detail.networks[0].id))
    parts.append(timestamp)
    ext = {"yaml": "yaml", "markdown": "md"}.get(detail.format, "json")
    return f"{'-'.join(p for p in parts if p)}.{ext}"


@read_router.get("/reports/preview", response_model=ReportDetail)
def report_preview(
    scenario: str | None = Query(default=None),
    scope: ReportScope = Query(default=ReportScope.full),
    format: ReportFormat = Query(default=ReportFormat.json),
    profile: RedactionProfile = Query(default=RedactionProfile.standard),
    network_id: str | None = Query(default=None),
    incident_id: str | None = Query(default=None),
    device: str | None = Query(default=None),
    preserve_friendly_names: bool | None = Query(default=None),
    hash_ieee_addresses: bool | None = Query(default=None),
    redact_hostnames: bool | None = Query(default=None),
    redact_ip_addresses: bool | None = Query(default=None),
    redact_network_names: bool | None = Query(default=None),
    include_timeline: bool | None = Query(default=None),
    include_raw_payloads: bool | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> ReportDetail:
    request = _build_request(
        scope=scope,
        format=format,
        profile=profile,
        network_id=network_id,
        incident_id=incident_id,
        device=device,
        preserve_friendly_names=preserve_friendly_names,
        hash_ieee_addresses=hash_ieee_addresses,
        redact_hostnames=redact_hostnames,
        redact_ip_addresses=redact_ip_addresses,
        redact_network_names=redact_network_names,
        include_timeline=include_timeline,
        include_raw_payloads=include_raw_payloads,
    )
    try:
        return ctx.data.report_preview(scenario, request, collector_status_dict(ctx))
    except ReportScopeAmbiguityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@mutation_router.post("/reports", response_model=ReportSummary)
def create_report(
    request: ReportRequest | None = None,
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> ReportSummary:
    req = request or ReportRequest()
    try:
        detail = generate_report(
            data=ctx.data,
            config=ctx.config,
            reporting=ctx.config.reporting,
            collector=collector_status_dict(ctx),
            request=req,
            scenario=scenario,
            repo=ctx.repo,
        )
    except ReportScopeAmbiguityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = store_report(ctx.repo, detail, req)
    return summary_from_detail(row, detail)


@read_router.get("/reports", response_model=list[ReportSummary])
def list_reports(ctx: AppContext = Depends(ctx_dep)) -> list[ReportSummary]:
    return [summary_from_row(row) for row in ctx.repo.reports.list_reports()]


@read_router.get("/reports/{report_id}", response_model=ReportDetail)
def get_report(
    report_id: str,
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> ReportDetail:
    report = ctx.data.get_stored_report(report_id, scenario)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@read_router.get("/reports/{report_id}/download")
def download_report(
    report_id: str,
    scenario: str | None = Query(default=None),
    ctx: AppContext = Depends(ctx_dep),
) -> Response:
    detail = ctx.data.get_stored_report(report_id, scenario)
    if not detail:
        raise HTTPException(status_code=404, detail="Report not found")

    if detail.format == "yaml":
        content = report_body_as_yaml(detail)
        media_type = "application/x-yaml"
    elif detail.format == "markdown":
        content = detail.markdown_summary
        media_type = "text/markdown"
    else:
        content = json.dumps(report_body_as_json(detail), indent=2)
        media_type = "application/json"

    filename = _report_filename(detail)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@mutation_router.delete("/reports/{report_id}")
def delete_report(
    report_id: str,
    ctx: AppContext = Depends(ctx_dep),
) -> dict[str, bool]:
    deleted = ctx.repo.reports.delete_report(report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"deleted": True}


@read_router.get("/topology")
def topology_overview(ctx: AppContext = Depends(ctx_dep)) -> dict:
    return topology_status_dict(ctx)


def _topology_inventory_counts(ctx: AppContext, network_id: str) -> dict[str, int]:
    devices = ctx.repo.list_devices(network_id)
    return {
        "device_count": len(devices),
        "router_count": sum(1 for device in devices if device.device_type == "Router"),
        "end_device_count": sum(1 for device in devices if device.device_type == "EndDevice"),
    }


@read_router.get("/topology/{network_id}")
def topology_network(network_id: str, ctx: AppContext = Depends(ctx_dep)) -> dict:
    network = ctx.repo.get_network(network_id)
    if network is None:
        raise HTTPException(status_code=404, detail="Network not found")
    latest = ctx.repo.get_latest_topology_snapshot(network_id)
    nodes = ctx.repo.list_topology_nodes(latest["snapshot_id"]) if latest else []
    links = ctx.repo.list_topology_links(latest["snapshot_id"]) if latest else []
    return {
        "network_id": network_id,
        "network_name": network.name,
        "latest_snapshot": latest,
        "nodes": nodes,
        "links": links,
        "inventory": _topology_inventory_counts(ctx, network_id),
        "layout_available": bool(nodes or links),
    }


@read_router.get("/topology/{network_id}/evidence-graph")
def topology_evidence_graph(network_id: str, ctx: AppContext = Depends(ctx_dep)) -> dict:
    from zigbeelens.services.evidence_graph import EvidenceGraphService, NetworkNotFoundError
    from zigbeelens.services.topology_facts_composition import topology_stale_threshold_hours

    try:
        return EvidenceGraphService(ctx.repo).build_with_network_topology_facts(
            network_id,
            stale_after_hours=topology_stale_threshold_hours(ctx.config),
        )
    except NetworkNotFoundError as err:
        raise HTTPException(status_code=404, detail="Network not found") from err


@read_router.get("/topology/{network_id}/snapshots")
def topology_snapshots(network_id: str, ctx: AppContext = Depends(ctx_dep)) -> dict:
    if ctx.repo.get_network(network_id) is None:
        raise HTTPException(status_code=404, detail="Network not found")
    return {"items": ctx.repo.list_topology_snapshots(network_id)}


@read_router.get("/topology/{network_id}/snapshots/compare")
def topology_snapshots_compare(
    network_id: str,
    base_snapshot_id: str | None = None,
    compare_snapshot_id: str | None = None,
    ctx: AppContext = Depends(ctx_dep),
) -> dict:
    """Read-only snapshot comparison: what changed between two usable
    (complete) topology snapshots.

    Defaults to the latest usable snapshot against the previous usable one.
    Failed/incomplete snapshots are never compared. The comparison is
    evidence-only: absence from the latest snapshot is described as "not
    present", never as lost/broken/offline, and route-hint changes come only
    from stored route-table evidence.
    """
    from zigbeelens.topology.compare import compare_snapshots

    if ctx.repo.get_network(network_id) is None:
        raise HTTPException(status_code=404, detail="Network not found")
    return compare_snapshots(
        ctx.repo,
        network_id,
        base_snapshot_id=base_snapshot_id,
        compare_snapshot_id=compare_snapshot_id,
    )


@read_router.get("/topology/{network_id}/devices/{ieee_address}/snapshot-history")
def topology_device_snapshot_history(
    network_id: str, ieee_address: str, ctx: AppContext = Depends(ctx_dep)
) -> dict:
    """Read-only device-led snapshot history: how one device looks in the
    latest usable snapshot compared with earlier usable snapshots.

    Per-device link and route-hint counts, availability tracking coverage
    per period, and an actionable comparison of each earlier snapshot
    against the latest (no_notable_change / changed / watch /
    worth_reviewing). Statuses describe snapshot comparison only, never
    device health, and use existing issue signals only.
    """
    from zigbeelens.services.evidence_graph import EvidenceGraphService
    from zigbeelens.services.topology_facts_composition import (
        build_device_snapshot_history_response,
        topology_stale_threshold_hours,
    )

    if ctx.repo.get_network(network_id) is None:
        raise HTTPException(status_code=404, detail="Network not found")
    return build_device_snapshot_history_response(
        ctx.repo,
        EvidenceGraphService(ctx.repo),
        network_id=network_id,
        device_ieee=ieee_address,
        stale_after_hours=topology_stale_threshold_hours(ctx.config),
    )


@read_router.get("/topology/{network_id}/snapshots/{snapshot_id}")
def topology_snapshot_detail(
    network_id: str, snapshot_id: str, ctx: AppContext = Depends(ctx_dep)
) -> dict:
    snapshot = ctx.repo.get_topology_snapshot(network_id, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {
        **snapshot,
        "nodes": ctx.repo.list_topology_nodes(snapshot_id),
        "links": ctx.repo.list_topology_links(snapshot_id),
    }


@mutation_router.post("/topology/{network_id}/capture")
def topology_capture(
    network_id: str,
    body: TopologyCaptureRequest,
    ctx: AppContext = Depends(ctx_dep),
) -> dict:
    service = get_topology_service()
    if service is None:
        raise HTTPException(status_code=403, detail="Topology is disabled")
    if body.confirmed is not True:
        raise HTTPException(status_code=400, detail=CAPTURE_WARNING)
    try:
        return service.request_capture(
            network_id,
            confirmed=True,
            requested_by=str(body.reason or "manual_user_capture"),
        )
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err)) from err
    except KeyError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


@read_router.get("/enrichment/status")
def enrichment_status(ctx: AppContext = Depends(ctx_dep)) -> dict:
    return enrichment_status_dict(ctx.repo)


@mutation_router.post("/enrichment/homeassistant")
def enrichment_homeassistant(body: dict, ctx: AppContext = Depends(ctx_dep)) -> dict:
    try:
        return apply_ha_enrichment(ctx.repo, body)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@mutation_router.delete("/enrichment/homeassistant")
def enrichment_homeassistant_delete(ctx: AppContext = Depends(ctx_dep)) -> dict:
    clear_ha_enrichment(ctx.repo)
    return {"cleared": True}


def include_api_routers(app, *, prefix: str) -> None:
    """Mount public/read/mutation routers under a single API prefix."""
    app.include_router(public_router, prefix=prefix)
    app.include_router(read_router, prefix=prefix)
    app.include_router(mutation_router, prefix=prefix)
