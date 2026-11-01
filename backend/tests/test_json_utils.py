"""Tolerant JSON extraction from model output."""

from __future__ import annotations

from app.services.json_utils import as_list, as_str, clamp_int, extract_json


def test_plain_json_object_parses():
    value, error = extract_json('{"a": 1, "b": "two"}')
    assert error is None
    assert value == {"a": 1, "b": "two"}


def test_fenced_json_block_parses():
    text = 'Here is the plan:\n```json\n{"tasks": [{"id": "t1"}]}\n```\nDone.'
    value, error = extract_json(text)
    assert error is None
    assert value["tasks"][0]["id"] == "t1"


def test_json_embedded_in_prose_parses():
    text = 'Sure. {"tasks": [], "summary": "ok"} That is the plan.'
    value, error = extract_json(text)
    assert error is None
    assert value["summary"] == "ok"


def test_json_array_parses():
    value, error = extract_json('[{"id": "a"}, {"id": "b"}]')
    assert error is None
    assert isinstance(value, list)
    assert len(value) == 2


def test_trailing_commas_are_repaired():
    value, error = extract_json('{"tasks": [{"id": "t1"},],}')
    assert error is None
    assert value["tasks"][0]["id"] == "t1"


def test_unparseable_text_returns_error_not_exception():
    value, error = extract_json("I could not produce a plan.")
    assert value is None
    assert error


def test_empty_input_returns_error():
    value, error = extract_json("")
    assert value is None
    assert error


def test_whitespace_only_input_returns_error():
    value, error = extract_json("   \n  ")
    assert value is None
    assert error


def test_none_input_is_handled():
    value, error = extract_json(None)
    assert value is None
    assert error


def test_single_quoted_json_is_repaired():
    value, error = extract_json("{'a': 1}")
    assert error is None
    assert value == {"a": 1}


# --- coercion helpers -----------------------------------------------------
def test_as_list_wraps_a_single_value():
    assert as_list("x") == ["x"]
    assert as_list(None) == []
    assert as_list([1, 2]) == [1, 2]


def test_as_str_uses_default_for_none():
    assert as_str(None, "fallback") == "fallback"
    assert as_str("value", "fallback") == "value"
    assert as_str(12, "fallback") == "12"


def test_clamp_int_bounds_values():
    assert clamp_int(50, low=1, high=9, default=5) == 9
    assert clamp_int(-3, low=1, high=9, default=5) == 1
    assert clamp_int("4", low=1, high=9, default=5) == 4
    assert clamp_int(None, low=1, high=9, default=5) == 5
    assert clamp_int("not a number", low=1, high=9, default=5) == 5
