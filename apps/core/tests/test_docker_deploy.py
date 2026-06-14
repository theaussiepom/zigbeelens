"""Docker/Compose deployment validation tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from zigbeelens.config import load_config

ROOT = Path(__file__).resolve().parents[3]
DOCKER = ROOT / "deploy" / "docker"

COMPOSE_FILES = [
    DOCKER / "docker-compose.example.yaml",
    DOCKER / "docker-compose.mosquitto.example.yaml",
    DOCKER / "docker-compose.traefik.example.yaml",
    DOCKER / "docker-compose.caddy.example.yaml",
    DOCKER / "docker-compose.beast-traefik.example.yaml",
]

CONFIG_FILES = [
    DOCKER / "config.example.yaml",
    DOCKER / "config.multi-network.example.yaml",
]


def test_config_examples_validate():
    for path in CONFIG_FILES:
        cfg = load_config(path)
        assert cfg.mode.mock is False
        assert cfg.storage.path == "/data/zigbeelens.sqlite"
        assert len(cfg.networks) >= 1
        assert cfg.features.mqtt_discovery is False


def test_multi_network_config_has_stable_ids():
    cfg = load_config(DOCKER / "config.multi-network.example.yaml")
    ids = [n.id for n in cfg.networks]
    assert ids == ["home", "home2"]
    assert len(set(ids)) == len(ids)


def test_config_examples_have_no_real_secrets():
    for path in CONFIG_FILES:
        text = path.read_text(encoding="utf-8")
        assert "secret-pass" not in text
        assert "hunter2" not in text
        assert 'password: ""' in text or "password:" in text


def test_compose_files_avoid_unsafe_patterns():
    banned = [
        ("docker.sock", "docker socket mount"),
        ("privileged: true", "privileged mode"),
        ("network_mode: host", "host networking"),
    ]
    for compose_path in COMPOSE_FILES:
        text = compose_path.read_text(encoding="utf-8")
        for pattern, label in banned:
            assert pattern not in text, f"{compose_path.name} contains {label}"


def test_dockerfile_healthcheck_uses_api_health():
    dockerfile = (DOCKER / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in dockerfile
    assert "/api/health" in dockerfile
    assert "timeout=5" in dockerfile
    assert "--interval=30s" in dockerfile
    assert "--start-period=30s" in dockerfile


def test_compose_files_do_not_duplicate_healthcheck():
    """Compose should inherit HEALTHCHECK from the image unless explicitly overridden."""
    for compose_path in COMPOSE_FILES:
        data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        service = data.get("services", {}).get("zigbeelens", {})
        assert "healthcheck" not in service, compose_path.name


def test_compose_exposes_port_8377():
    data = yaml.safe_load((DOCKER / "docker-compose.example.yaml").read_text(encoding="utf-8"))
    ports = data["services"]["zigbeelens"]["ports"]
    assert "8377:8377" in ports


def test_dockerfile_defaults():
    dockerfile = (DOCKER / "Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8377" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/api/health" in dockerfile
    assert "ZIGBEELENS_CONFIG=/config/config.yaml" in dockerfile
    assert "USER zigbeelens" in dockerfile


def test_caddy_example_supports_sse_and_documents_embedded_view():
    caddyfile = (DOCKER / "Caddyfile.example").read_text(encoding="utf-8")
    assert "flush_interval -1" in caddyfile
    compose = (DOCKER / "docker-compose.caddy.example.yaml").read_text(encoding="utf-8")
    assert "hacs-embedded-view.md" in compose
    assert "8443:443" in compose


def test_beast_traefik_example_documents_embedded_view():
    compose = (DOCKER / "docker-compose.beast-traefik.example.yaml").read_text(encoding="utf-8")
    headers = (ROOT / "deploy/traefik/security-headers-zigbeelens.yaml.example").read_text(
        encoding="utf-8"
    )
    assert "securityHeadersZigbeeLens@file" in compose
    assert "zigbeelens.${DOMAIN}" in compose
    assert "8377:8377" in compose
    assert "underground" in compose
    assert "frame-ancestors" in headers
    assert "hass.theaussiepom.me" in headers


def test_hacs_embedded_view_doc_exists():
    doc = (ROOT / "docs" / "hacs-embedded-view.md").read_text(encoding="utf-8")
    assert "optional" in doc.lower()
    assert "Open Full Dashboard" in doc
    assert "docker-compose.beast-traefik.example.yaml" in doc


def test_docker_docs_mention_security():
    docker_md = (ROOT / "docs" / "docker.md").read_text(encoding="utf-8")
    assert "trusted" in docker_md.lower() or "reverse proxy" in docker_md.lower()
    assert "read-only" in docker_md.lower()
