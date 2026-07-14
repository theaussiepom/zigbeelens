"""Central report redaction: profiles, stable hashing, and secret scrubbing.

This module never leaks secrets. It redacts known secret keys, MQTT/connection
credentials, and — depending on the chosen profile — hostnames, IP addresses,
IEEE addresses, friendly names, and network names. Identifier redaction uses a
per-report salt so the same input maps to the same redacted token within a
single report, but never across reports (non-reversible).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from zigbeelens.config.redaction import REDACTED, redact_connection_string
from zigbeelens.schemas import RedactionOptions, RedactionProfile, ReportRedactionStatus

# Exact secret key names (case-insensitive).
_SECRET_EXACT = {
    "password",
    "pass",
    "passwd",
    "secret",
    "token",
    "auth",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "network_key",
    "networkkey",
    "secret_key",
    "client_secret",
    "install_code",
    "psk",
    "pre_shared_key",
}

# Secret key suffixes. Note: bare "key" / "linkquality" are intentionally NOT
# redacted; only specific suffixes are.
_SECRET_SUFFIX = (
    "_password",
    "_passwd",
    "_secret",
    "_token",
    "_key",
    "_credential",
    "_credentials",
    "_apikey",
)

_USERNAME_KEYS = {"username", "user"}

# Categorical / enum string fields must not pass through free-text scrubbing.
# Friendly names like "Router" or "Battery" would otherwise corrupt values such
# as device_type or power_source when those tokens appear as substrings.
_STRUCTURED_STRING_KEYS = frozenset(
    {
        "device_type",
        "power_source",
        "availability",
        "interview_state",
        "bridge_state",
        "primary",
        "severity",
        "confidence",
        "classification",
        "overall_state",
        "overall_severity",
        "health_state",
        "state",
        "status",
        "priority",
        "headline_code",
        "label_code",
        "dimension",
        "scope_type",
        "card_type",
        "action_group",
        "subject_type",
        "code",
    }
)

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b")


def is_secret_key(key: str) -> bool:
    lower = key.lower()
    if lower in _SECRET_EXACT:
        return True
    return any(lower.endswith(suffix) for suffix in _SECRET_SUFFIX)


@dataclass
class ResolvedRedaction:
    profile: str
    redact_usernames: bool
    redact_hostnames: bool
    redact_ip_addresses: bool
    hash_ieee: bool
    friendly_mode: str  # preserved | labeled | hashed
    network_mode: str  # preserved | labeled | hashed
    include_timeline: bool
    include_raw_payloads: bool

    @property
    def network_anon(self) -> bool:
        return self.network_mode != "preserved"

    def to_status(self) -> ReportRedactionStatus:
        return ReportRedactionStatus(
            applied=True,
            profile=self.profile,
            mqtt_credentials=True,
            secrets=True,
            hostnames=self.redact_hostnames,
            ip_addresses=self.redact_ip_addresses,
            ieee_addresses_hashed=self.hash_ieee,
            friendly_names=self.friendly_mode,
            network_names=self.network_mode,
        )


_PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "standard": {
        "redact_usernames": False,
        "redact_hostnames": False,
        "redact_ip_addresses": False,
        "hash_ieee": True,
        "friendly_mode": "preserved",
        "network_mode": "preserved",
    },
    "strict": {
        "redact_usernames": True,
        "redact_hostnames": True,
        "redact_ip_addresses": True,
        "hash_ieee": True,
        "friendly_mode": "hashed",
        "network_mode": "hashed",
    },
    "public_safe": {
        "redact_usernames": True,
        "redact_hostnames": True,
        "redact_ip_addresses": True,
        "hash_ieee": True,
        "friendly_mode": "labeled",
        "network_mode": "labeled",
    },
}


def resolve_redaction(
    options: RedactionOptions,
    *,
    default_profile: str = "standard",
    default_include_raw: bool = False,
) -> ResolvedRedaction:
    profile = (options.profile or RedactionProfile(default_profile)).value
    base = _PROFILE_DEFAULTS.get(profile, _PROFILE_DEFAULTS["standard"])

    redact_hostnames = (
        options.redact_hostnames if options.redact_hostnames is not None else base["redact_hostnames"]
    )
    redact_ips = (
        options.redact_ip_addresses
        if options.redact_ip_addresses is not None
        else base["redact_ip_addresses"]
    )
    hash_ieee = (
        options.hash_ieee_addresses if options.hash_ieee_addresses is not None else base["hash_ieee"]
    )

    friendly_mode = base["friendly_mode"]
    if options.preserve_friendly_names is True:
        friendly_mode = "preserved"
    elif options.preserve_friendly_names is False and friendly_mode == "preserved":
        friendly_mode = "labeled"

    network_mode = base["network_mode"]
    if options.redact_network_names is True and network_mode == "preserved":
        network_mode = "labeled"
    elif options.redact_network_names is False:
        network_mode = "preserved"

    include_timeline = options.include_timeline if options.include_timeline is not None else True
    include_raw = (
        options.include_raw_payloads
        if options.include_raw_payloads is not None
        else default_include_raw
    )

    return ResolvedRedaction(
        profile=profile,
        redact_usernames=base["redact_usernames"],
        redact_hostnames=redact_hostnames,
        redact_ip_addresses=redact_ips,
        hash_ieee=hash_ieee,
        friendly_mode=friendly_mode,
        network_mode=network_mode,
        include_timeline=include_timeline,
        include_raw_payloads=include_raw,
    )


def _report_network_records(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic union of scoped report networks and configured networks.

    Order: report.networks first, then previously unseen config_summary.networks.
    Deduplicate by non-empty string network ID (first record wins; later records
    may fill missing name / base_topic).
    """
    scoped = report.get("networks") or []
    config = report.get("config_summary")
    configured: list[Any] = []
    if isinstance(config, dict):
        configured = config.get("networks") or []

    records: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    def _append(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        nid = raw.get("id")
        if isinstance(nid, str) and nid:
            existing = by_id.get(nid)
            if existing is not None:
                if not existing.get("name") and isinstance(raw.get("name"), str):
                    existing["name"] = raw["name"]
                if not existing.get("base_topic") and isinstance(raw.get("base_topic"), str):
                    existing["base_topic"] = raw["base_topic"]
                return
            # Copy so merge fills do not mutate the report dict in place.
            record = dict(raw)
            by_id[nid] = record
            records.append(record)
            return
        records.append(dict(raw))

    if isinstance(scoped, list):
        for item in scoped:
            _append(item)
    if isinstance(configured, list):
        for item in configured:
            _append(item)
    return records


@dataclass
class Redactor:
    resolved: ResolvedRedaction
    salt: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        self._friendly_map: dict[str, str] = {}
        self._friendly_counter = 0
        self._ieee_map: dict[str, str] = {}
        self._net_id_map: dict[str, str] = {}
        self._net_name_map: dict[str, str] = {}
        self._net_topic_map: dict[str, str] = {}
        self._net_label_counter = 0
        self._text_replacements: list[tuple[str, str]] = []

    # -- hashing ---------------------------------------------------------
    def _hash(self, value: str, prefix: str) -> str:
        digest = hashlib.sha256(f"{self.salt}:{value}".encode()).hexdigest()[:8]
        return f"{prefix}_{digest}"

    def _ieee(self, value: str) -> str:
        if not self.resolved.hash_ieee or not value:
            return value
        if value not in self._ieee_map:
            self._ieee_map[value] = self._hash(value, "ieee")
        return self._ieee_map[value]

    def _friendly(self, value: str) -> str:
        mode = self.resolved.friendly_mode
        if mode == "preserved" or not value:
            return value
        if value not in self._friendly_map:
            if mode == "hashed":
                self._friendly_map[value] = self._hash(value, "device")
            else:  # labeled
                self._friendly_counter += 1
                self._friendly_map[value] = f"device_{self._friendly_counter:03d}"
        return self._friendly_map[value]

    def _network_id(self, value: str) -> str:
        """Stable per-report network-ID mapping, including orphaned IDs."""
        if not self.resolved.network_anon or not value:
            return value
        if value in self._net_id_map:
            return self._net_id_map[value]
        if self.resolved.network_mode == "hashed":
            label = self._hash(value, "network")
        else:
            self._net_label_counter += 1
            label = f"network_{self._net_label_counter:03d}"
        self._net_id_map[value] = label
        return label

    # -- network maps ----------------------------------------------------
    def _build_network_maps(self, networks: list[dict[str, Any]]) -> None:
        if not self.resolved.network_anon:
            return
        for i, net in enumerate(networks):
            nid = net.get("id")
            name = net.get("name")
            topic = net.get("base_topic")
            if isinstance(nid, str):
                label = self._network_id(nid)
            else:
                label = (
                    self._hash(str(i), "network")
                    if self.resolved.network_mode == "hashed"
                    else f"network_{i + 1:03d}"
                )
            if isinstance(name, str):
                self._net_name_map[name] = label
            if isinstance(topic, str):
                self._net_topic_map[topic] = (
                    self._hash(topic, "topic")
                    if self.resolved.network_mode == "hashed"
                    else f"topic_{i + 1:03d}"
                )

    def _collect(self, obj: Any) -> None:
        """Pre-pass: collect identifiers so free text can be scrubbed too."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = k.lower()
                if lk == "ieee_address" and isinstance(v, str):
                    self._ieee(v)
                elif lk == "device_ieees" and isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            self._ieee(item)
                elif lk == "network_id" and isinstance(v, str):
                    self._network_id(v)
                elif lk == "network_ids" and isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            self._network_id(item)
                elif lk == "friendly_name" and isinstance(v, str):
                    self._friendly(v)
                else:
                    self._collect(v)
        elif isinstance(obj, list):
            for item in obj:
                self._collect(item)

    def _build_text_replacements(self) -> None:
        pairs: list[tuple[str, str]] = []
        if self.resolved.hash_ieee:
            pairs.extend(self._ieee_map.items())
        if self.resolved.friendly_mode != "preserved":
            pairs.extend(self._friendly_map.items())
        if self.resolved.network_anon:
            pairs.extend(self._net_name_map.items())
            pairs.extend(self._net_id_map.items())
            pairs.extend(self._net_topic_map.items())
        # Replace longer originals first so substrings do not corrupt matches.
        self._text_replacements = sorted(pairs, key=lambda p: len(p[0]), reverse=True)

    # -- string scrubbing ------------------------------------------------
    def _scrub_text(self, value: str) -> str:
        for original, replacement in self._text_replacements:
            if original and original in value:
                value = value.replace(original, replacement)
        if self.resolved.redact_ip_addresses:
            value = _IPV4_RE.sub("[redacted-ip]", value)
            value = _IPV6_RE.sub("[redacted-ip]", value)
        return value

    def _redact_server(self, value: str) -> str:
        value = redact_connection_string(value)
        if self.resolved.redact_ip_addresses:
            value = _IPV4_RE.sub("[redacted-ip]", value)
            value = _IPV6_RE.sub("[redacted-ip]", value)
        if self.resolved.redact_hostnames:
            value = re.sub(r"(://)([^/:@]+@)?[^/:?#@]+", r"\1\2[redacted-host]", value)
        return value

    # -- traversal -------------------------------------------------------
    def _walk(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                out[k] = self._walk_value(k, v)
            return out
        if isinstance(obj, list):
            return [self._walk(item) for item in obj]
        if isinstance(obj, str):
            return self._scrub_text(obj)
        return obj

    def _walk_value(self, key: str, value: Any) -> Any:
        lk = key.lower()
        if is_secret_key(lk):
            return REDACTED
        if lk in _USERNAME_KEYS and self.resolved.redact_usernames:
            return REDACTED if value else value
        if lk == "ieee_address" and isinstance(value, str):
            return self._ieee(value)
        if lk == "device_ieees" and isinstance(value, list):
            return [
                self._ieee(item) if isinstance(item, str) else item for item in value
            ]
        if lk == "network_id" and isinstance(value, str):
            return self._network_id(value)
        if lk == "network_ids" and isinstance(value, list):
            return [
                self._network_id(x) if isinstance(x, str) else x for x in value
            ]
        if lk == "base_topic" and isinstance(value, str):
            return self._net_topic_map.get(value, value) if self.resolved.network_anon else value
        if lk == "id" and isinstance(value, str) and self.resolved.network_anon and value in self._net_id_map:
            return self._net_id_map[value]
        if lk == "name" and isinstance(value, str) and self.resolved.network_anon and value in self._net_name_map:
            return self._net_name_map[value]
        if lk == "friendly_name" and isinstance(value, str):
            return self._friendly(value)
        if lk in _STRUCTURED_STRING_KEYS and isinstance(value, str):
            return value
        if lk in ("server", "mqtt_server") and isinstance(value, str):
            return self._redact_server(value)
        if lk in ("storage_path", "path") and isinstance(value, str) and self.resolved.redact_hostnames:
            return REDACTED
        if isinstance(value, (dict, list)):
            return self._walk(value)
        if isinstance(value, str):
            return self._scrub_text(value)
        return value

    def redact(self, report: dict[str, Any]) -> dict[str, Any]:
        """Return a redacted copy of a report dict."""
        self._build_network_maps(_report_network_records(report))
        self._collect(report)
        self._build_text_replacements()
        return self._walk(report)
