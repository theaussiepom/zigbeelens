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


def test_redact_connection_string_empty_username_password():
    sentinel = "credential-sentinel"
    value = f"mqtt://:{sentinel}@broker:1883"
    redacted = redact_connection_string(value)
    assert sentinel not in redacted
    assert ":***@" in redacted
    assert "broker" in redacted
    assert "1883" in redacted


def test_redact_dict_secrets_empty_username_password_uri():
    sentinel = "credential-sentinel"
    redacted = redact_dict_secrets({"server": f"mqtt://:{sentinel}@broker:1883"})
    assert sentinel not in redacted["server"]
    assert "broker" in redacted["server"]
    assert "1883" in redacted["server"]


def test_redact_connection_string_hostless_empty_username_password():
    sentinel = "credential-sentinel"
    assert redact_connection_string(f"mqtt://:{sentinel}@") == REDACTED
    assert sentinel not in redact_connection_string(f"mqtt://:{sentinel}@")


def test_redact_connection_string_userinfo_still_useful():
    redacted = redact_connection_string("mqtt://user:password@broker:1883")
    assert "password" not in redacted.split("@", 1)[0] or ":***@" in redacted
    assert "user:***@" in redacted
    assert "broker" in redacted
    assert "1883" in redacted


def test_redact_connection_string_percent_encoded_userinfo():
    # urlparse may leave userinfo percent-encoded; never echo the password form.
    value = "mqtt://%75ser:%70assword-sentinel@broker:1883"
    redacted = redact_connection_string(value)
    assert "%70assword-sentinel" not in redacted
    assert "password-sentinel" not in redacted
    assert "broker" in redacted
    assert "1883" in redacted
    assert "***" in redacted


def test_redact_connection_string_username_only_may_remain():
    value = "mqtt://onlyuser@broker:1883"
    assert redact_connection_string(value) == value


def test_redact_connection_string_ipv6_host_remains_bracketed():
    redacted = redact_connection_string("mqtt://user:secret@[::1]:1883")
    assert "secret" not in redacted
    assert "[::1]" in redacted
    assert "1883" in redacted
    assert "user:***@" in redacted


@pytest.mark.parametrize(
    "value",
    [
        "mqtt://user:credential-sentinel@[broken",
        "mqtt://:credential-sentinel@[broken",
    ],
)
def test_redact_dict_secrets_malformed_credential_authority_fail_closed(value: str):
    sentinel = "credential-sentinel"
    assert sentinel in value
    assert redact_connection_string(value) == REDACTED
    redacted = redact_dict_secrets({"server": value})
    assert redacted["server"] == REDACTED
    assert sentinel not in redacted["server"]


def test_redact_dict_secrets_malformed_credential_uri_nested_structures():
    sentinel = "credential-sentinel"
    malformed = f"mqtt://user:{sentinel}@[broken"
    payload = {
        "items": [malformed],
        "nested": {"mqtt_server": malformed, "ok": True},
        "tuple_like": (malformed,),
        "connection": f"mqtt://:{sentinel}@[broken",
        "endpoint": malformed,
    }
    redacted = redact_dict_secrets(payload)
    blob = str(redacted)
    assert sentinel not in blob
    assert redacted["items"][0] == REDACTED
    assert redacted["nested"]["mqtt_server"] == REDACTED
    assert redacted["nested"]["ok"] is True
    assert redacted["tuple_like"][0] == REDACTED
    assert redacted["connection"] == REDACTED
    assert redacted["endpoint"] == REDACTED


def test_redact_dict_secrets_valid_password_uri_remains_useful():
    redacted = redact_dict_secrets({"server": "mqtt://user:password@broker:1883"})
    assert redacted["server"] == "mqtt://user:***@broker:1883"
    assert "password" not in redacted["server"].split("@", 1)[0]
    assert "broker" in redacted["server"]
    assert "1883" in redacted["server"]


def test_redact_dict_secrets_safe_uri_without_credentials_unchanged():
    value = "mqtt://broker:1883/path?client_id=safe&token_count=2"
    redacted = redact_dict_secrets({"server": value})
    assert redacted["server"] == value


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
