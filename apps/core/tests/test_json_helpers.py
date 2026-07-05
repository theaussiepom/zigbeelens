"""Shared JSON helper tests."""

from zigbeelens.util.json_helpers import parse_json_list


def test_parse_json_list_empty():
    assert parse_json_list(None) == []
    assert parse_json_list("") == []


def test_parse_json_list_valid_array():
    assert parse_json_list('["a", {"summary": "b"}]') == ["a", {"summary": "b"}]


def test_parse_json_list_invalid_returns_empty():
    assert parse_json_list("{") == []
    assert parse_json_list('{"not": "list"}') == []
