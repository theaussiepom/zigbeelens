"""API token grammar shared by SecurityConfig and Bearer header parsing."""

from __future__ import annotations

import base64
import os
import traceback
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from zigbeelens.api.auth import AUTH_DETAIL
from zigbeelens.config import ConfigError, load_config
from zigbeelens.config.api_token import (
    API_TOKEN_MAX_LENGTH,
    API_TOKEN_MIN_LENGTH,
    is_api_token_shape,
    parse_bearer_authorization_header,
    reject_invalid_api_token,
)
from zigbeelens.config.loader import format_validation_error
from zigbeelens.config.models import SecurityConfig
from zigbeelens.main import create_app

VALID_ALNUM = "a" * 32
VALID_BASE64 = base64.b64encode(os.urandom(36)).decode("ascii")  # typically +/ and =
VALID_URLSAFE = "Ab0-_~." + ("x" * 25)
VALID_DOT_TILDE = ("z" * 30) + ".~"


def _assert_absent_from_formatted(exc: ValidationError, secret: str) -> None:
    rendered = format_validation_error(exc)
    assert secret not in rendered
    assert secret not in str(ConfigError(rendered))


def _assert_secret_absent(exc: BaseException, secret: str) -> None:
    assert secret not in str(exc)
    assert secret not in repr(exc)
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert secret not in rendered


@pytest.mark.parametrize(
    "token",
    [VALID_ALNUM, VALID_BASE64, VALID_URLSAFE, VALID_DOT_TILDE],
)
def test_accepted_api_tokens_pass_shape_and_config(token: str):
    assert is_api_token_shape(token)
    cfg = SecurityConfig(api_token=token)
    assert cfg.api_token is not None
    assert cfg.api_token.get_secret_value() == token


@pytest.mark.parametrize(
    "token",
    [
        "has space inside____________",  # internal space
        "a" * 31,  # too short
        "token,with,commas,,,,,,,,,,,",
        "token:with:colons:::::::::::",
        '"quoted-token-value-here!!!!!"',
        "hash#inside#################",
        "emoji-👍-not-ascii-xxxxxxxxx",
        "pad=middle=stillmore========",
        "a" * (API_TOKEN_MAX_LENGTH + 1),
        "tab\tinsidexxxxxxxxxxxxxxxxx",
        "newline\ninsidexxxxxxxxxxxxxxx",
    ],
)
def test_rejected_api_tokens_fail_config_without_echo(token: str):
    with pytest.raises(ValidationError) as exc_info:
        SecurityConfig(api_token=token)
    _assert_absent_from_formatted(exc_info.value, token)
    assert not is_api_token_shape(token)


def test_internal_space_and_comma_rejected_explicitly():
    spaced = "abcd efghijklmnopqrstuvwxyz01234"
    comma = "abcdefghijklmnopqrstuvwxyz012345,"
    for token in (spaced, comma):
        assert len(token) >= API_TOKEN_MIN_LENGTH
        assert not is_api_token_shape(token)
        with pytest.raises(ValidationError) as exc_info:
            SecurityConfig(api_token=token)
        _assert_absent_from_formatted(exc_info.value, token)


def test_session_secret_allows_punctuation_outside_token68():
    punct = "session-secret-with:punct;#@$!" + ("y" * 4)
    cfg = SecurityConfig(session_secret=punct)
    assert cfg.session_secret is not None
    assert cfg.session_secret.get_secret_value() == punct
    with pytest.raises(ValidationError) as exc_info:
        SecurityConfig(api_token=punct)
    _assert_absent_from_formatted(exc_info.value, punct)


def test_header_grammar_matches_config_grammar():
    for token in (VALID_ALNUM, VALID_BASE64, VALID_URLSAFE, VALID_DOT_TILDE):
        assert parse_bearer_authorization_header(f"Bearer {token}") == token
        assert parse_bearer_authorization_header(f"bearer  {token}") == token
    for bad in (
        f"Bearer {VALID_ALNUM[:16]} {VALID_ALNUM[16:]}",
        f"Bearer {VALID_ALNUM},extra",
        f"Bearer\t{VALID_ALNUM}",
        f"Basic {VALID_ALNUM}",
        f"Bearer {VALID_ALNUM} ",
    ):
        with pytest.raises(ValueError):
            parse_bearer_authorization_header(bad)


def test_accepted_configured_tokens_authenticate(tmp_path: Path, monkeypatch):
    for index, token in enumerate((VALID_ALNUM, VALID_BASE64, VALID_URLSAFE)):
        cfg = tmp_path / f"cfg-{index}.yaml"
        cfg.write_text(
            f"""
mode:
  mock: true
storage:
  path: {tmp_path / f'db-{index}.sqlite'}
networks: []
security:
  api_token: "{token}"
""",
            encoding="utf-8",
        )
        monkeypatch.setenv("ZIGBEELENS_CONFIG", str(cfg))
        with TestClient(create_app(str(cfg))) as client:
            denied = client.get("/api/dashboard")
            assert denied.status_code == 401
            assert denied.json()["detail"] == AUTH_DETAIL
            ok = client.get(
                "/api/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert ok.status_code == 200, token


def test_env_file_and_alias_use_same_api_token_validation(tmp_path: Path, monkeypatch):
    base = tmp_path / "base.yaml"
    base.write_text(
        f"""
mode:
  mock: true
storage:
  path: {tmp_path / 'base.sqlite'}
networks: []
""",
        encoding="utf-8",
    )
    bad = "bad token with spaces!!!!!!!!!!!!"
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN", bad)
    with pytest.raises(ConfigError) as exc_info:
        load_config(base)
    _assert_secret_absent(exc_info.value, bad)

    monkeypatch.delenv("ZIGBEELENS_SECURITY_API_TOKEN", raising=False)
    token_file = tmp_path / "tok"
    token_file.write_text(bad + "\n", encoding="utf-8")
    monkeypatch.setenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", str(token_file))
    with pytest.raises(ConfigError) as exc_info:
        load_config(base)
    _assert_secret_absent(exc_info.value, bad)

    monkeypatch.delenv("ZIGBEELENS_SECURITY_API_TOKEN_FILE", raising=False)
    monkeypatch.setenv("ZIGBEELENS_API_KEY", bad)
    with pytest.raises(ConfigError) as exc_info:
        load_config(base)
    _assert_secret_absent(exc_info.value, bad)


def test_reject_helper_never_echoes():
    bad = "comma,token,value,abcdefghijklmnop"
    with pytest.raises(ValueError) as exc_info:
        reject_invalid_api_token(bad)
    _assert_secret_absent(exc_info.value, bad)
