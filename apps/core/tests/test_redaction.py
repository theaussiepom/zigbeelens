import pytest
from pydantic import SecretStr

from zigbeelens.config.models import AppConfig, SecurityConfig
from zigbeelens.config.redaction import (
    REDACTED,
    is_secret_key,
    redact_connection_string,
    redact_dict_secrets,
    redact_mqtt_server,
)

_EXACT_URI_SECRET_KEYS = (
    "password",
    "passphrase",
    "secret",
    "session_secret",
    "client_secret",
    "token",
    "api_token",
    "access_token",
    "refresh_token",
    "api_key",
    "api-key",
    "authorization",
    "private_key",
    "network_key",
    "install_code",
)

_SUFFIX_URI_SECRET_KEYS = (
    "oauth_token",
    "broker_password",
    "signing_private_key",
)


def test_redact_mqtt_server_with_credentials():
    redacted = redact_mqtt_server("mqtt://mosquitto:1883", "zigbeelens")
    assert "secret" not in redacted
    assert "***" in redacted
    assert "mosquitto" in redacted


def test_redact_mqtt_server_query_and_fragment_credentials():
    redacted = redact_mqtt_server(
        "mqtt://user:pw@broker:1883/path?password=qsecret&token=qtoken&client_id=safe#api_key=fsecret",
        "user",
    )
    assert "pw" not in redacted
    assert "qsecret" not in redacted
    assert "qtoken" not in redacted
    assert "fsecret" not in redacted
    assert "client_id=safe" in redacted
    assert "broker" in redacted



def test_redact_dict_secrets():
    data = {"mqtt": {"password": "secret-pass", "username": "user"}}
    redacted = redact_dict_secrets(data)
    assert redacted["mqtt"]["password"] == "***"
    assert redacted["mqtt"]["username"] == "user"
    assert data["mqtt"]["password"] == "secret-pass"


def test_redact_nested_lists_and_secretstr():
    payload = {
        "items": [
            {"api_token": "tok" * 12, "name": "a"},
            {"mqtt_password": "nested-secret", "ok": True},
        ],
        "tuple_like": ({"session_secret": "sess" * 8},),
        "wrapped": SecretStr("secret-value-should-mask"),
    }
    redacted = redact_dict_secrets(payload)
    assert redacted["items"][0]["api_token"] == REDACTED
    assert redacted["items"][0]["name"] == "a"
    assert redacted["items"][1]["mqtt_password"] == REDACTED
    assert redacted["tuple_like"][0]["session_secret"] == REDACTED
    assert redacted["wrapped"] == REDACTED


def test_redact_preserves_safe_configured_and_count_fields():
    payload = {
        "api_token_configured": True,
        "session_secret_configured": False,
        "token_count": 3,
        "subscribed_topics_count": 12,
        "api_token": "should-hide",
    }
    redacted = redact_dict_secrets(payload)
    assert redacted["api_token_configured"] is True
    assert redacted["session_secret_configured"] is False
    assert redacted["token_count"] == 3
    assert redacted["subscribed_topics_count"] == 12
    assert redacted["api_token"] == REDACTED


def test_redact_connection_string_userinfo_and_query():
    value = "mqtt://user:hunter2@broker:1883/path?password=abc&token=xyz#frag"
    redacted = redact_connection_string(value)
    assert "hunter2" not in redacted
    assert "password=***" in redacted
    assert "token=***" in redacted
    assert "broker" in redacted


@pytest.mark.parametrize("key", _EXACT_URI_SECRET_KEYS)
def test_redact_mqtt_server_redacts_exact_secret_query_keys(key: str):
    sentinel = f"sentinel-{key.replace('-', '_')}"
    server = f"mqtt://broker:1883/path?client_id=safe&{key}={sentinel}&token_count=2"
    redacted = redact_mqtt_server(server)
    assert sentinel not in redacted
    assert "client_id=safe" in redacted
    assert "token_count=2" in redacted
    assert f"{key}=***" in redacted
    assert "broker" in redacted
    assert is_secret_key(key)


@pytest.mark.parametrize("key", _SUFFIX_URI_SECRET_KEYS)
def test_redact_mqtt_server_redacts_suffix_secret_query_keys(key: str):
    sentinel = f"suffix-{key}"
    server = f"mqtt://broker:1883/?{key}={sentinel}&client_id=keep"
    redacted = redact_mqtt_server(server)
    assert sentinel not in redacted
    assert f"{key}=***" in redacted
    assert "client_id=keep" in redacted


def test_redact_connection_string_matches_secret_key_policy():
    value = (
        "mqtt://broker:1883/path"
        "?client_secret=cs1&authorization=Bearer-x&network_key=nk1"
        "&install_code=ic1&oauth_token=ot1&broker_password=bp1"
        "&signing_private_key=spk1&client_id=visible&token_count=9"
        "#api-key=hyphenated"
    )
    redacted = redact_connection_string(value)
    for sentinel in ("cs1", "Bearer-x", "nk1", "ic1", "ot1", "bp1", "spk1", "hyphenated"):
        assert sentinel not in redacted
    assert "client_id=visible" in redacted
    assert "token_count=9" in redacted
    assert "broker" in redacted


def test_redact_dict_secrets_uri_detection_uses_extended_secret_keys():
    payload = {
        "server": "mqtt://broker:1883/?client_secret=leak-cs&client_id=ok",
        "alt": "https://example/path?authorization=Bearer-leak&token_source=env",
        "note": "plain text",
    }
    redacted = redact_dict_secrets(payload)
    assert "leak-cs" not in redacted["server"]
    assert "client_id=ok" in redacted["server"]
    assert "Bearer-leak" not in redacted["alt"]
    assert "token_source=env" in redacted["alt"]
    assert redacted["note"] == "plain text"


def test_redact_preserves_url_decoded_secret_keys():
    # parse_qsl decodes keys; %70assword → password
    server = "mqtt://broker:1883/?%70assword=decoded-secret&client_id=safe"
    redacted = redact_mqtt_server(server)
    assert "decoded-secret" not in redacted
    assert "client_id=safe" in redacted


def test_redact_dict_secrets_redacts_credential_uris():
    payload = {
        "server": "mqtt://user:leak@host:1883",
        "note": "plain text",
    }
    redacted = redact_dict_secrets(payload)
    assert "leak" not in redacted["server"]
    assert redacted["note"] == "plain text"


def test_appconfig_dump_redaction_masks_security_and_mqtt():
    token = "e" * 32
    config = AppConfig(
        security=SecurityConfig(api_token=token, session_secret="f" * 32),
        mqtt={"password": "mqtt-password-value", "username": "u"},
    )
    dumped = config.model_dump(mode="python")
    redacted = redact_dict_secrets(dumped)
    assert token not in str(redacted)
    assert "mqtt-password-value" not in str(redacted)
    assert redacted["security"]["api_token"] == REDACTED
    assert redacted["mqtt"]["password"] == REDACTED
    assert redacted["mqtt"]["username"] == "u"
