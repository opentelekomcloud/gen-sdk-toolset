"""LLM client pieces with no I/O: schema lookup, timeout policy, model-text parsing.

* Schemas load by id from an explicit root; anything unreadable is SchemaNotFound.
* Truncated JSON is never repaired; a missing validator fails closed.
"""

from __future__ import annotations

import sys
import types

import pytest

from tools.llm.parsing import Parser, jsonschema_validator, parse_object
from tools.llm.port import Request
from tools.llm.schemas import SchemaNotFound, SchemaRepository, sha_of
from tools.llm.timeouts import TimeoutPolicy


def ask(**kw) -> Request:
    return Request(**{"model": "m", "system": "s", "user": "u", "purpose": "p", **kw})


def _explode(data, schema):
    raise AssertionError("the validator must not be called")


@pytest.fixture
def repo(tmp_path) -> SchemaRepository:
    (tmp_path / "good.schema.json").write_text('{"type": "object"}', encoding="utf-8")
    (tmp_path / "broken.schema.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "list.schema.json").write_text("[1, 2]", encoding="utf-8")
    return SchemaRepository(tmp_path)


# --------------------------------------------------------------------------- #
# SchemaRepository
# --------------------------------------------------------------------------- #
def test_schema_loads_by_id(repo) -> None:
    schema = repo.get("good")
    assert schema.body == {"type": "object"}
    assert schema.id == "good"
    assert schema.sha


def test_missing_schema_file_is_not_found(repo) -> None:
    with pytest.raises(SchemaNotFound):
        repo.get("nope")


def test_broken_schema_json_is_not_found(repo) -> None:
    with pytest.raises(SchemaNotFound):
        repo.get("broken")


def test_schema_that_is_not_an_object_is_not_found(repo) -> None:
    with pytest.raises(SchemaNotFound):
        repo.get("list")


def test_invalid_utf8_is_not_an_escaping_exception(repo, tmp_path) -> None:
    (tmp_path / "bytes.schema.json").write_bytes(b'{"a": "\xff\xfe"}')
    with pytest.raises(SchemaNotFound):
        repo.get("bytes")


def test_nan_in_a_schema_is_refused(repo, tmp_path) -> None:
    (tmp_path / "nan.schema.json").write_text('{"a": NaN}', encoding="utf-8")
    with pytest.raises(SchemaNotFound):
        repo.get("nan")


def test_infinity_in_a_schema_is_refused(repo, tmp_path) -> None:
    (tmp_path / "inf.schema.json").write_text('{"a": Infinity}', encoding="utf-8")
    with pytest.raises(SchemaNotFound):
        repo.get("inf")


@pytest.mark.parametrize("bad", ["../secret", "a/b", "a\\b", ""])
def test_path_traversal_is_refused(repo, bad) -> None:
    with pytest.raises(SchemaNotFound):
        repo.get(bad)


def test_schema_is_read_once(repo, tmp_path) -> None:
    first = repo.get("good")
    (tmp_path / "good.schema.json").write_text('{"type": "array"}', encoding="utf-8")
    assert repo.get("good") is first


def test_sha_ignores_key_order() -> None:
    assert sha_of({"a": 1, "b": 2}) == sha_of({"b": 2, "a": 1})


def test_sha_changes_with_content() -> None:
    assert sha_of({"a": 1}) != sha_of({"a": 2})


# --------------------------------------------------------------------------- #
# TimeoutPolicy
# --------------------------------------------------------------------------- #
def test_long_call_gets_the_long_timeout() -> None:
    assert TimeoutPolicy().seconds_for(ask(max_tokens=9000)) == 180.0


def test_short_call_gets_the_short_timeout() -> None:
    assert TimeoutPolicy().seconds_for(ask(max_tokens=1600)) == 45.0


def test_timeout_boundary_is_not_long() -> None:
    assert TimeoutPolicy().seconds_for(ask(max_tokens=8000)) == 45.0


# --------------------------------------------------------------------------- #
# parse_object
# --------------------------------------------------------------------------- #
def test_plain_object_parses() -> None:
    assert parse_object('{"a": 1}').data == {"a": 1}


def test_fenced_object_parses() -> None:
    assert parse_object('```json\n{"a": 1}\n```').data == {"a": 1}


def test_fenced_object_without_language_parses() -> None:
    assert parse_object('```\n{"a": 1}\n```').data == {"a": 1}


def test_single_line_fence_parses() -> None:
    assert parse_object('```{"a": 1}```').data == {"a": 1}


def test_unclosed_fence_around_a_complete_object_parses() -> None:
    assert parse_object('```json\n{"a": 1}').data == {"a": 1}


def test_chatter_around_a_complete_object_is_stripped() -> None:
    text = 'Here is the result:\n{"a": 1}\ndone'
    assert parse_object(text).data == {"a": 1}


def test_truncated_json_is_not_repaired() -> None:
    parsed = parse_object('{"a": [1, 2')
    assert parsed.failure == "invalid_json"
    assert parsed.data is None


def test_braces_around_garbage_are_invalid_json() -> None:
    parsed = parse_object("see {this} and that")
    assert parsed.failure == "invalid_json"
    assert parsed.data is None


def test_top_level_array_is_refused() -> None:
    parsed = parse_object("[1, 2]")
    assert parsed.failure == "invalid_json"
    assert "list" in parsed.error


def test_empty_text_is_invalid_json() -> None:
    assert parse_object("").failure == "invalid_json"


def test_non_ascii_text_survives() -> None:
    assert parse_object('{"a": "Zoë Brontë"}').data == {"a": "Zoë Brontë"}


def test_long_unparsable_text_is_previewed_not_dumped() -> None:
    parsed = parse_object("x" * 500)
    assert parsed.failure == "invalid_json"
    assert parsed.error.endswith("…")
    assert len(parsed.error) < 300


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def test_parser_is_built_on_parse_object() -> None:
    text = 'chatter {"a": 1} more'
    parsed = Parser(validator=None).parse_and_validate(text, None)
    assert parsed.data == parse_object(text).data


def test_validation_failure_is_named() -> None:
    def refuse(data, schema):
        raise ValueError("chunks is required")

    parsed = Parser(validator=refuse).parse_and_validate('{"a": 1}', {"type": "object"})
    assert parsed.failure == "schema_invalid"
    assert "chunks is required" in parsed.error
    assert parsed.data == {"a": 1}


def test_passing_validation_returns_the_data() -> None:
    parsed = Parser(validator=lambda data, schema: None).parse_and_validate(
        '{"a": 1}', {"type": "object"}
    )
    assert parsed.failure == ""
    assert parsed.data == {"a": 1}


def test_no_schema_means_no_validation() -> None:
    assert Parser(validator=_explode).parse_and_validate('{"a": 1}', None).data == {
        "a": 1
    }


def test_missing_validator_fails_closed() -> None:
    parsed = Parser(validator=None).parse_and_validate('{"a": 1}', {"type": "object"})
    assert parsed.failure == "config"
    assert "jsonschema" in parsed.error


def test_missing_validator_is_fine_when_no_schema_was_asked_for() -> None:
    assert Parser(validator=None).parse_and_validate('{"a": 1}', None).failure == ""


def test_broken_json_skips_validation() -> None:
    assert Parser(validator=_explode).parse_and_validate("{", {}).failure == (
        "invalid_json"
    )


# --------------------------------------------------------------------------- #
# jsonschema discovery
# --------------------------------------------------------------------------- #
def test_no_validator_when_jsonschema_is_absent(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    assert jsonschema_validator() is None
    parsed = Parser().parse_and_validate('{"a": 1}', {"type": "object"})
    assert parsed.failure == "config"


def test_default_parser_validates_with_jsonschema_when_present(monkeypatch) -> None:
    seen = []

    def validate(data, schema):
        seen.append((data, schema))
        if "a" not in data:
            raise ValueError("'a' is a required property")

    fake = types.ModuleType("jsonschema")
    fake.validate = validate
    monkeypatch.setitem(sys.modules, "jsonschema", fake)

    parser = Parser()
    assert parser.parse_and_validate('{"a": 1}', {"type": "object"}).failure == ""
    refused = parser.parse_and_validate('{"b": 1}', {"type": "object"})
    assert refused.failure == "schema_invalid"
    assert "'a' is a required property" in refused.error
    assert seen == [({"a": 1}, {"type": "object"}), ({"b": 1}, {"type": "object"})]
