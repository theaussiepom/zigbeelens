
from zigbeelens.config.redaction import redact_dict_secrets, redact_mqtt_server


def test_redact_mqtt_server_with_credentials():
    redacted = redact_mqtt_server("mqtt://mosquitto:1883", "zigbeelens")
    assert "secret" not in redacted
    assert "***" in redacted
    assert "mosquitto" in redacted


def test_redact_dict_secrets():
    data = {"mqtt": {"password": "secret-pass", "username": "user"}}
    redacted = redact_dict_secrets(data)
    assert redacted["mqtt"]["password"] == "***"
    assert redacted["mqtt"]["username"] == "user"
