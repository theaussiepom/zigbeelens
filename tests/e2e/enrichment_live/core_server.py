"""Live ZigbeeLens Core process for the enrichment/UI convergence E2E test."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket

import uvicorn

from zigbeelens.config.models import NetworkConfig
from zigbeelens.db.connection import Database
from zigbeelens.main import create_app
from zigbeelens.storage.repository import Repository

IEEE = "0x00124b0024abcd01"


def _write_config(state_dir: Path) -> Path:
    config_path = state_dir / "config.yaml"
    database_path = state_dir / "zigbeelens.sqlite"
    config_path.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 8377
mode:
  mock: false
mqtt:
  server: mqtt://127.0.0.1:1883
  client_id: zigbeelens-enrichment-live-e2e
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
storage:
  path: {database_path}
  retention_days: 7
features:
  mqtt_collector: false
  mqtt_discovery: false
  bridge_logs: true
  device_payload_history: true
  manual_network_map: false
  automatic_network_map: false
topology:
  enabled: false
  manual_capture_enabled: false
  automatic_capture_enabled: false
  startup_scan: false
security:
  mode: local
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _seed_live_device(state_dir: Path) -> None:
    database = Database(state_dir / "zigbeelens.sqlite")
    database.migrate()
    repository = Repository(database)
    repository.sync_networks(
        [NetworkConfig(id="home", name="Home", base_topic="zigbee2mqtt")]
    )
    repository.upsert_device(
        network_id="home",
        ieee_address=IEEE,
        friendly_name="source-lamp",
        device_type="Router",
        power_source="Mains",
        interview_state="successful",
    )
    repository.ensure_device_current_state("home", IEEE)
    repository.update_device_current_state(
        network_id="home",
        ieee_address=IEEE,
        availability="online",
        linkquality=121,
    )
    database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--url-file", type=Path, required=True)
    args = parser.parse_args()

    args.state_dir.mkdir(parents=True, exist_ok=True)
    config_path = _write_config(args.state_dir)
    _seed_live_device(args.state_dir)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.set_inheritable(True)
    port = listener.getsockname()[1]
    args.url_file.write_text(f"http://127.0.0.1:{port}\n", encoding="utf-8")

    app = create_app(str(config_path))
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    server.run(sockets=[listener])


if __name__ == "__main__":
    main()
