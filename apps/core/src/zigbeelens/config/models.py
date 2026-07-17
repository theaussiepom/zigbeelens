"""Application configuration models."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from zigbeelens.config.security_types import SecurityMode
from zigbeelens.mock.fixtures import DEFAULT_SCENARIO

MIN_SECURITY_SECRET_LENGTH = 32


def _reject_invalid_secret(value: object) -> SecretStr:
    """Validate an optional secret without echoing the rejected value."""
    if isinstance(value, SecretStr):
        raw = value.get_secret_value()
    elif isinstance(value, str):
        raw = value
    else:
        raise ValueError("must be a string")

    if raw == "":
        raise ValueError("must not be empty")
    if raw != raw.strip():
        raise ValueError("must not have leading or trailing whitespace")
    if any(ord(ch) < 32 for ch in raw):
        raise ValueError("must not contain control characters")
    if len(raw) < MIN_SECURITY_SECRET_LENGTH:
        raise ValueError(f"must be at least {MIN_SECURITY_SECRET_LENGTH} characters")
    return SecretStr(raw)


class SecurityConfig(BaseModel):
    mode: SecurityMode = SecurityMode.local
    api_token: SecretStr | None = None
    session_secret: SecretStr | None = None

    @field_validator("api_token", "session_secret", mode="before")
    @classmethod
    def validate_optional_secret(cls, value: object) -> SecretStr | None:
        if value is None:
            return None
        return _reject_invalid_secret(value)

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> SecurityConfig:
        if self.mode is SecurityMode.authenticated and self.api_token is None:
            raise ValueError(
                "api_token is required when mode is authenticated"
            )
        return self


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8377, ge=1, le=65535)


class ModeConfig(BaseModel):
    mock: bool = True
    default_scenario: str = DEFAULT_SCENARIO


class MqttTlsConfig(BaseModel):
    enabled: bool = False
    reject_unauthorized: bool = True


class MqttConfig(BaseModel):
    server: str = "mqtt://mosquitto:1883"
    username: str = ""
    password: str = ""
    client_id: str = "zigbeelens"
    tls: MqttTlsConfig = Field(default_factory=MqttTlsConfig)


class NetworkConfig(BaseModel):
    id: str
    name: str
    base_topic: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("network id must not be empty")
        return cleaned


class StorageConfig(BaseModel):
    path: str = "./data/zigbeelens.sqlite"
    retention_days: int = Field(default=7, ge=1)


class DiagnosticsConfig(BaseModel):
    incident_window_seconds: int = Field(default=180, ge=1)
    stale_after_hours: int = Field(default=24, ge=1)
    low_battery_percent: int = Field(default=20, ge=0, le=100)
    weak_link_threshold: int = Field(default=40, ge=0, le=255)
    flapping_threshold: int = Field(default=3, ge=1)
    recently_unstable_window_hours: int = Field(default=24, ge=1)
    bridge_stale_after_minutes: int = Field(default=10, ge=1)
    mains_stale_after_hours: int = Field(default=12, ge=1)
    battery_stale_after_hours: int = Field(default=48, ge=1)
    incident_watch_window_minutes: int = Field(default=30, ge=1)
    incident_resolution_grace_minutes: int = Field(default=5, ge=1)
    network_wide_device_percent: int = Field(default=25, ge=1, le=100)
    network_wide_min_devices: int = Field(default=5, ge=1)
    correlated_min_devices: int = Field(default=2, ge=2)
    stale_cluster_min_devices: int = Field(default=3, ge=1)
    low_battery_cluster_min_devices: int = Field(default=3, ge=1)
    interview_failure_min_devices: int = Field(default=2, ge=1)


class FeaturesConfig(BaseModel):
    mqtt_collector: bool = True
    mqtt_discovery: bool = False
    bridge_logs: bool = True
    device_payload_history: bool = True
    manual_network_map: bool = False
    automatic_network_map: bool = False


class TopologyConfig(BaseModel):
    enabled: bool = True
    manual_capture_enabled: bool = False
    automatic_capture_enabled: bool = False
    automatic_capture_interval_hours: int = Field(default=24, ge=1)
    startup_scan: bool = True
    startup_stable_delay_seconds: int = Field(default=60, ge=0)
    refresh_interval_seconds: int = Field(default=0, ge=0)
    capture_on_incident: bool = False
    # Count cap per network; storage.retention_days bounds snapshots by age
    # independently. 30 keeps enough history for "last known link" evidence
    # to survive restart bursts (startup scans) at ~1 MB per snapshot.
    max_snapshots_per_network: int = Field(default=30, ge=1)
    warn_before_capture: bool = True


class MqttDiscoveryConfig(BaseModel):
    enabled: bool = True
    topic_prefix: str = "homeassistant"
    state_topic_prefix: str = "zigbeelens"
    retain: bool = True
    device_name: str = "ZigbeeLens"
    object_id_prefix: str = "zigbeelens"


class ReportingConfig(BaseModel):
    max_recent_events: int = Field(default=100, ge=1)
    max_metric_samples_per_device: int = Field(default=50, ge=1)
    max_availability_changes_per_device: int = Field(default=50, ge=1)
    include_raw_payloads: bool = False
    default_profile: str = "standard"


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    mode: ModeConfig = Field(default_factory=ModeConfig)
    mqtt: MqttConfig = Field(default_factory=MqttConfig)
    networks: list[NetworkConfig] = Field(default_factory=list)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    diagnostics: DiagnosticsConfig = Field(default_factory=DiagnosticsConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    mqtt_discovery: MqttDiscoveryConfig = Field(default_factory=MqttDiscoveryConfig)
    topology: TopologyConfig = Field(default_factory=TopologyConfig)
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    @field_validator("networks")
    @classmethod
    def unique_network_ids(cls, networks: list[NetworkConfig]) -> list[NetworkConfig]:
        ids = [n.id for n in networks]
        if len(ids) != len(set(ids)):
            raise ValueError("network ids must be unique")
        return networks
