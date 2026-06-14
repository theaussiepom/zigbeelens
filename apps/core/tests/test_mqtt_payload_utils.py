from zigbeelens.mqtt.payload_utils import redact_payload_dict, redact_payload_text


def test_redact_password_in_payload():
    raw = b'{"password":"secret","mqtt":{"pass":"x"},"linkquality":50}'
    redacted = redact_payload_text(raw)
    assert "secret" not in redacted
    assert "***" in redacted
    assert "linkquality" in redacted


def test_redact_network_key():
    data = {"network_key": "abcd1234", "channel": 15}
    redacted = redact_payload_dict(data)
    assert redacted["network_key"] == "***"
    assert redacted["channel"] == 15
