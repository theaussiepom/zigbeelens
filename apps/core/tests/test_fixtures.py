from zigbeelens.mock.fixtures import BUILDERS, get_scenario


def test_each_scenario_has_dashboard_and_devices():
    for sid in BUILDERS:
        data = get_scenario(sid)
        assert data.dashboard.scenario == sid or data.id == sid
        assert data.dashboard.current_finding.summary
        assert len(data.dashboard.current_finding.limitations) >= 0


def test_four_devices_scenario_is_incident():
    data = get_scenario("four_devices_same_room_unavailable")
    assert data.dashboard.active_incident_count >= 1
    assert data.dashboard.overall_severity.value == "incident"
    assert len(data.incidents) >= 1
    assert len(data.dashboard.top_affected_devices) == 4


def test_bridge_offline_critical():
    data = get_scenario("bridge_offline")
    assert data.networks[0].bridge_state.value == "offline"
    assert data.dashboard.overall_severity.value == "critical"
