"""API response-shape parity tests for the evidence-graph endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

EVIDENCE_GRAPH_TOP_LEVEL_KEYS = (
    "network_id",
    "network_name",
    "data_source",
    "latest_snapshot",
    "nodes",
    "links",
    "layout_available",
    "latest_layout_limited",
    "inventory",
    "history_window",
    "historical_neighbors",
    "historical_routes",
    "last_known_links",
    "last_known_window",
    "passive_hints",
    "passive_hint_window",
    "investigations",
    "investigation_counts",
    "device_stats",
    "device_stats_window",
    "limitations",
    "counts",
    "topology_facts",
)

EVIDENCE_GRAPH_COUNT_KEYS = (
    "latest_snapshot_neighbor_edges",
    "latest_snapshot_route_edges",
    "historical_neighbor_edges",
    "historical_route_edges",
    "recent_missing_link_count_total",
    "last_known_link_count",
    "passive_hint_count_available",
    "passive_hint_count_total",
    "passive_hint_count_drawn",
    "hidden_for_readability",
    "known_inventory_devices",
    "observed_topology_nodes",
)


def test_evidence_graph_api_response_shape_parity(topology_client: TestClient):
    res = topology_client.get("/api/topology/home/evidence-graph")
    assert res.status_code == 200
    body = res.json()

    assert set(body.keys()) == set(EVIDENCE_GRAPH_TOP_LEVEL_KEYS)

    counts = body["counts"]
    assert isinstance(counts, dict)
    assert set(counts.keys()) == set(EVIDENCE_GRAPH_COUNT_KEYS)

    # Client-rendering subsets are unknown server-side — null, never zero.
    assert counts["passive_hint_count_drawn"] is None
    assert counts["hidden_for_readability"] is None

    assert isinstance(body["investigation_counts"], dict)
    assert isinstance(body["inventory"], dict)
    assert isinstance(body["historical_neighbors"], list)
    assert isinstance(body["historical_routes"], list)
    assert isinstance(body["last_known_links"], list)
    assert isinstance(body["passive_hints"], list)
    assert isinstance(body["investigations"], list)
    assert isinstance(body["device_stats"], dict)
    assert isinstance(body["limitations"], list)

    topology_facts = body["topology_facts"]
    assert set(topology_facts.keys()) == {"stale_threshold_hours", "network_facts"}
    assert topology_facts["stale_threshold_hours"] is None
    assert isinstance(topology_facts["network_facts"], list)


def test_evidence_graph_api_unknown_network_returns_404_detail(topology_client: TestClient):
    res = topology_client.get("/api/topology/nope/evidence-graph")
    assert res.status_code == 404
    assert res.json() == {"detail": "Network not found"}
