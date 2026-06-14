from zigbeelens.config.models import AppConfig, NetworkConfig
from zigbeelens.db.connection import Database
from zigbeelens.services.empty_state import build_empty_dashboard
from zigbeelens.storage.repository import Repository


def test_empty_dashboard_unknown_state(tmp_path):
    config = AppConfig(
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")]
    )
    db = Database(tmp_path / "empty.sqlite")
    db.migrate()
    repo = Repository(db)
    repo.sync_networks(config.networks)

    dash = build_empty_dashboard(config, repo.list_networks())
    assert dash.overall_severity.value == "watch"
    assert "No Zigbee2MQTT data has been collected yet" in dash.current_finding.summary
    assert dash.current_finding.limitations
    assert len(dash.networks) == 1

    db.close()


def test_empty_dashboard_from_config_when_no_db_networks():
    config = AppConfig(
        networks=[NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")]
    )
    dash = build_empty_dashboard(config, [])
    assert len(dash.networks) == 1
    assert dash.networks[0].id == "home"
