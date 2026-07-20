from zigbeelens.mock.fixtures import BUILDERS, get_scenario


def test_each_scenario_has_dashboard_and_devices():
    for sid in BUILDERS:
        data = get_scenario(sid)
        assert data.dashboard.scenario == sid or data.id == sid
        assert data.dashboard.decision_summary.overall_status
        assert data.dashboard.networks
        for device in data.devices:
            assert device.decision is not None
            assert device.decision.status


def test_four_devices_scenario_is_incident():
    data = get_scenario("four_devices_same_room_unavailable")
    assert data.dashboard.active_incident_count >= 1
    assert data.dashboard.decision_summary.overall_status in {
        "review_first",
        "worth_reviewing",
    }
    assert len(data.incidents) >= 1
    assert sum(1 for d in data.devices if d.availability.value == "offline") == 4


def test_bridge_offline_critical():
    data = get_scenario("bridge_offline")
    assert data.networks[0].bridge_state.value == "offline"
    assert data.dashboard.networks[0].active_incident_severity.value == "critical"
