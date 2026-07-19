"""Mock diagnostic fixture provider."""

from __future__ import annotations

from zigbeelens.mock.fixtures import (
    BUILDERS,
    ScenarioData,
    build_report_preview,
    device_detail_from_summary,
    get_scenario,
    list_scenarios,
)
from zigbeelens.storage.incident_collection import (
    cursor_from_incident_row,
    decode_incident_collection_cursor,
    encode_incident_collection_cursor,
    lifecycle_rank,
)


class MockProvider:
    def __init__(self, scenario_id: str) -> None:
        self.scenario_id = scenario_id
        self._data: ScenarioData | None = None

    @property
    def data(self) -> ScenarioData:
        if self._data is None:
            self._data = get_scenario(self.scenario_id)
        return self._data

    @staticmethod
    def list_scenarios() -> list[dict[str, str]]:
        return list_scenarios()

    @staticmethod
    def is_valid_scenario(scenario_id: str) -> bool:
        return scenario_id in BUILDERS

    def dashboard(self):
        return self.data.dashboard

    def networks(self):
        return self.data.networks

    def network(self, network_id: str):
        for net in self.data.networks:
            if net.id == network_id:
                return net
        return None

    def devices(self, network_id: str | None = None):
        if network_id:
            return [d for d in self.data.devices if d.network_id == network_id]
        return list(self.data.devices)

    def device(self, network_id: str, ieee_address: str):
        for d in self.data.devices:
            if d.network_id == network_id and d.ieee_address == ieee_address:
                return device_detail_from_summary(d, self.data)
        return None

    def device_story(self, network_id: str, ieee_address: str):
        return self.data.device_stories.get((network_id, ieee_address))

    def routers(self):
        from zigbeelens.mock.fixtures import conclusion
        from zigbeelens.schemas import Confidence, IncidentScope, RouterRisk, Severity

        router_devices = [d for d in self.data.devices if d.device_type.value == "Router"]
        risks = self.data.router_risks or self.data.dashboard.router_risks
        risk_map = {(r.network_id, r.ieee_address): r for r in risks}
        items: list[RouterRisk] = []
        for d in router_devices:
            key = (d.network_id, d.ieee_address)
            if key in risk_map:
                items.append(risk_map[key])
            else:
                items.append(
                    RouterRisk(
                        network_id=d.network_id,
                        ieee_address=d.ieee_address,
                        friendly_name=d.friendly_name,
                        availability=d.availability,
                        linkquality=d.linkquality,
                        last_seen=d.last_seen,
                        possibly_dependent_devices=None,
                        correlated_affected_devices=0,
                        risk=conclusion(
                            "router_ok",
                            Severity.healthy,
                            IncidentScope.router_candidate,
                            Confidence.high,
                            f"{d.friendly_name} shows no elevated router risk.",
                        ),
                    )
                )
        return items

    def _incident_status(self, inc) -> str:
        return inc.status.value if hasattr(inc.status, "value") else str(inc.status)

    def _filtered_incidents(self, query):
        filtered = []
        for inc in self.data.incidents:
            status = self._incident_status(inc)
            if status not in query.status_filter:
                continue
            if query.updated_after is not None and not (inc.updated_at > query.updated_after):
                continue
            if query.network_id is not None and query.network_id not in inc.network_ids:
                continue
            if query.device_ieee is not None:
                if not any(
                    ref.network_id == query.network_id and ref.ieee_address == query.device_ieee
                    for ref in inc.affected_devices
                ):
                    continue
            filtered.append(inc)
        return filtered

    def _ordered_incidents(self, incidents):
        by_rank: dict[int, list] = {}
        for inc in incidents:
            by_rank.setdefault(lifecycle_rank(self._incident_status(inc)), []).append(inc)
        ordered = []
        for rank in sorted(by_rank):
            ordered.extend(
                sorted(
                    by_rank[rank],
                    key=lambda inc: (inc.updated_at, inc.id),
                    reverse=True,
                )
            )
        return ordered

    def incidents_page(self, query):
        """Paginated scenario incidents matching the live collection contract."""
        filtered = self._filtered_incidents(query)
        ordered = self._ordered_incidents(filtered)
        total = len(ordered)

        if query.cursor is not None:
            cursor = decode_incident_collection_cursor(
                query.cursor,
                expected_filter_signature=query.filter_signature,
            )
            continued = []
            for inc in ordered:
                rank = lifecycle_rank(self._incident_status(inc))
                after = (
                    rank > cursor.lifecycle_rank
                    or (rank == cursor.lifecycle_rank and inc.updated_at < cursor.updated_at)
                    or (
                        rank == cursor.lifecycle_rank
                        and inc.updated_at == cursor.updated_at
                        and inc.id < cursor.incident_id
                    )
                )
                if after:
                    continued.append(inc)
            ordered = continued

        window = ordered[: query.limit + 1]
        has_more = len(window) > query.limit
        page_items = window[: query.limit]
        # Collection rows do not include timeline (parity with live list composition).
        items = [inc.model_copy(update={"timeline": []}) for inc in page_items]
        next_cursor = None
        if has_more and page_items:
            last = page_items[-1]
            next_cursor = encode_incident_collection_cursor(
                cursor_from_incident_row(
                    {
                        "id": last.id,
                        "lifecycle_state": self._incident_status(last),
                        "updated_at": last.updated_at,
                    },
                    filter_signature=query.filter_signature,
                )
            )
        return {
            "items": items,
            "total": total,
            "limit": query.limit,
            "next_cursor": next_cursor,
        }

    def incident(self, incident_id: str):
        for inc in self.data.incidents:
            if inc.id == incident_id:
                return inc
        return None

    def timeline(self, network_id: str | None = None):
        events = self.data.timeline or self.data.dashboard.recent_timeline
        if network_id:
            events = [e for e in events if e.network_id == network_id]
        return sorted(events, key=lambda e: e.timestamp, reverse=True)

    def report_preview(self):
        return build_report_preview(self.data)
