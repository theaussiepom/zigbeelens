
from pydantic import SecretStr

from zigbeelens.config.models import AppConfig, SecurityConfig
from zigbeelens.config.redaction import (
    REDACTED,
    redact_connection_string,
    redact_dict_secrets,
    redact_mqtt_server,
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
