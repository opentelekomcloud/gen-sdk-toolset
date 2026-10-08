"""LLM service behaviours, driven through a fake transport.

* One call: route -> schema -> provider body -> transport -> parsed ``Result``.
* Every failure comes back as ``Result(ok=False, failure=...)`` with the facts
  that travelled with it (``sent``, ``http_status``, ``usage``).
* A reply cut at ``max_tokens`` is ``truncated``, never a success.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from tools.llm import service as service_module
from tools.llm.parsing import Parser
from tools.llm.port import FAILURES, Request
from tools.llm.providers import OpenAICompatibleAdapter
from tools.llm.schemas import SchemaRepository
from tools.llm.service import LLMService, Route
from tools.llm.timeouts import TimeoutPolicy
from tools.llm.transport.base import HTTP_ERROR, OK, RATE_LIMITED, TransportResult

MODEL = "qwen3.6-35b"


def ask(**kw) -> Request:
    return Request(
        **{"model": MODEL, "system": "s", "user": "u", "purpose": "refine", **kw}
    )


def body(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def completion(content='{"chunks": []}', usage=None, finish_reason="stop"):
    return {
        "model": MODEL,
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": usage
        if usage is not None
        else {"prompt_tokens": 10, "completion_tokens": 5},
    }


class FakeTransport:
    """Answers with the queued results in order, repeating the last one."""

    def __init__(self, *results: TransportResult) -> None:
        self.results = list(results)
        self.calls: list[dict] = []

    def send(self, path, body, *, timeout):
        self.calls.append({"path": path, "body": body, "timeout": timeout})
        index = min(len(self.calls) - 1, len(self.results) - 1)
        return self.results[index]


class _FixedDatetime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 9, 1, 12, 0, tzinfo=tz)


@pytest.fixture
def schemas(tmp_path) -> SchemaRepository:
    (tmp_path / "batch.schema.json").write_text('{"type": "object"}', encoding="utf-8")
    return SchemaRepository(tmp_path)


@pytest.fixture
def make_service(schemas):
    def make(transport, *, parser=None, routes=None) -> LLMService:
        route = Route(adapter=OpenAICompatibleAdapter(), transport=transport)
        return LLMService(
            routes=routes if routes is not None else {MODEL: route},
            schemas=schemas,
            timeouts=TimeoutPolicy(),
            parser=parser or Parser(validator=lambda data, schema: None),
        )

    return make


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_schema_request_returns_text_and_data(make_service) -> None:
    transport = FakeTransport(
        TransportResult(status=OK, raw=body(completion()), elapsed_ms=99)
    )
    result = make_service(transport).complete(ask(schema_id="batch"))
    assert result.ok
    assert result.data == {"chunks": []}
    assert result.text == '{"chunks": []}'
    assert result.failure == ""


def test_result_carries_provenance_facts(make_service, schemas, monkeypatch) -> None:
    monkeypatch.setattr(service_module, "datetime", _FixedDatetime)
    transport = FakeTransport(
        TransportResult(status=OK, raw=body(completion()), elapsed_ms=99)
    )
    result = make_service(transport).complete(ask(schema_id="batch"))
    assert result.model == MODEL
    assert result.route == "openai-compatible"
    assert result.purpose == "refine"
    assert result.usage["completion_tokens"] == 5
    assert result.ms == 99
    assert result.schema_sha == schemas.get("batch").sha
    assert result.requested_at == "2026-09-01T12:00:00+00:00"
    assert result.finish_reason == "stop"


def test_requested_at_is_timezone_aware_iso(make_service) -> None:
    transport = FakeTransport(TransportResult(status=OK, raw=body(completion())))
    result = make_service(transport).complete(ask())
    assert datetime.fromisoformat(result.requested_at).tzinfo == UTC


def test_sent_travels_from_the_transport_to_the_result(make_service) -> None:
    """A request that never left (DNS, refused) cost nothing and says nothing
    about the model; a caller must be able to tell it from a real failure."""
    transport = FakeTransport(
        TransportResult(status="network", sent=False, error="dns")
    )
    result = make_service(transport).complete(ask())
    assert not result.ok
    assert not result.sent

    transport = FakeTransport(
        TransportResult(status="network", sent=True, error="reset")
    )
    assert make_service(transport).complete(ask()).sent


def test_http_status_travels_to_the_result(make_service) -> None:
    transport = FakeTransport(
        TransportResult(
            status=HTTP_ERROR,
            http_status=401,
            raw=b'{"error": {"message": "bad key"}}',
        )
    )
    result = make_service(transport).complete(ask())
    assert result.failure == "http"
    assert result.http_status == 401
    assert result.sent

    transport = FakeTransport(
        TransportResult(status=OK, raw=body(completion()), http_status=200)
    )
    assert make_service(transport).complete(ask()).http_status == 200


def test_config_failure_was_never_sent(make_service) -> None:
    result = make_service(FakeTransport()).complete(ask(model="nobody/knows"))
    assert result.failure == "config"
    assert not result.sent


def test_without_schema_there_is_no_data(make_service) -> None:
    transport = FakeTransport(
        TransportResult(status=OK, raw=body(completion(content="just text")))
    )
    result = make_service(transport).complete(ask())
    assert result.ok
    assert result.text == "just text"
    assert result.data is None


def test_timeout_comes_from_the_policy(make_service) -> None:
    transport = FakeTransport(TransportResult(status=OK, raw=body(completion())))
    make_service(transport).complete(ask(max_tokens=9000))
    assert transport.calls[0]["timeout"] == 180.0
    make_service(transport).complete(ask(max_tokens=1000))
    assert transport.calls[1]["timeout"] == 45.0


def test_schema_reaches_the_provider_body(make_service) -> None:
    transport = FakeTransport(TransportResult(status=OK, raw=body(completion())))
    make_service(transport).complete(ask(schema_id="batch"))
    sent = transport.calls[0]["body"]
    assert sent["response_format"]["json_schema"]["schema"] == {"type": "object"}


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def test_unknown_model_never_reaches_the_transport(make_service) -> None:
    transport = FakeTransport(TransportResult(status=OK, raw=body(completion())))
    result = make_service(transport).complete(ask(model="no/such-model"))
    assert result.failure == "config"
    assert "no/such-model" in result.error
    assert transport.calls == []


def test_missing_schema_is_config_and_costs_no_call(make_service) -> None:
    transport = FakeTransport(TransportResult(status=OK, raw=body(completion())))
    result = make_service(transport).complete(ask(schema_id="missing"))
    assert result.failure == "config"
    assert not result.sent
    assert transport.calls == []


def test_schema_without_a_repository_is_config_and_costs_no_call() -> None:
    transport = FakeTransport(TransportResult(status=OK, raw=body(completion())))
    route = Route(adapter=OpenAICompatibleAdapter(), transport=transport)
    service = LLMService(routes={MODEL: route})
    result = service.complete(ask(schema_id="batch"))
    assert result.failure == "config"
    assert "no repository" in result.error
    assert result.route == "openai-compatible"
    assert not result.sent
    assert transport.calls == []


# --------------------------------------------------------------------------- #
# Failures
# --------------------------------------------------------------------------- #
def test_transport_failure_is_named_publicly(make_service) -> None:
    transport = FakeTransport(
        TransportResult(status=RATE_LIMITED, http_status=429, error="HTTP 429")
    )
    result = make_service(transport).complete(ask())
    assert not result.ok
    assert result.failure == "rate_limit"
    assert result.failure in FAILURES


def test_http_error_keeps_the_provider_message(make_service) -> None:
    payload = {"error": {"message": "no such model"}}
    transport = FakeTransport(
        TransportResult(
            status=HTTP_ERROR, http_status=400, raw=body(payload), error="HTTP 400"
        )
    )
    result = make_service(transport).complete(ask())
    assert result.failure == "http"
    assert "no such model" in result.error


def test_empty_answer_is_a_failure(make_service) -> None:
    transport = FakeTransport(
        TransportResult(status=OK, raw=body(completion(content="")))
    )
    result = make_service(transport).complete(ask())
    assert result.failure == "empty"


def test_invalid_json_when_a_schema_was_asked_for(make_service) -> None:
    transport = FakeTransport(
        TransportResult(status=OK, raw=body(completion(content="{not json")))
    )
    result = make_service(transport).complete(ask(schema_id="batch"))
    assert result.failure == "invalid_json"
    assert result.text == "{not json"


def test_unavailable_validation_is_config_not_a_silent_pass(make_service) -> None:
    transport = FakeTransport(TransportResult(status=OK, raw=body(completion())))
    service = make_service(transport, parser=Parser(validator=None))
    result = service.complete(ask(schema_id="batch"))
    assert not result.ok
    assert result.failure == "config"


def test_schema_invalid_keeps_the_parsed_data(make_service) -> None:
    def refuse(data, schema):
        raise ValueError("chunks is required")

    transport = FakeTransport(TransportResult(status=OK, raw=body(completion())))
    service = make_service(transport, parser=Parser(validator=refuse))
    result = service.complete(ask(schema_id="batch"))
    assert result.failure == "schema_invalid"
    assert result.data == {"chunks": []}


def test_usage_survives_a_failure(make_service) -> None:
    transport = FakeTransport(
        TransportResult(status=OK, raw=body(completion(content="")))
    )
    result = make_service(transport).complete(ask())
    assert result.usage["prompt_tokens"] == 10


# --------------------------------------------------------------------------- #
# Truncation at max_tokens
# --------------------------------------------------------------------------- #
def test_truncated_is_a_public_failure() -> None:
    assert "truncated" in FAILURES


def test_cut_off_text_without_a_schema_is_truncated_not_ok(make_service) -> None:
    """Without a schema nothing else notices a cut: the partial text would reach
    the caller as a success and the missing part would vanish."""
    payload = completion(content="def refine(x):\n    return", finish_reason="length")
    transport = FakeTransport(TransportResult(status=OK, raw=body(payload)))
    result = make_service(transport).complete(ask(max_tokens=512))
    assert not result.ok
    assert result.failure == "truncated"
    assert result.text == "def refine(x):\n    return"
    assert "max_tokens=512" in result.error
    assert result.finish_reason == "length"
    assert result.usage["completion_tokens"] == 5
    assert result.data is None


def test_cut_off_broken_json_is_truncated_not_invalid_json(make_service) -> None:
    """The cut is the cause, so the failure names it: reporting ``invalid_json``
    would send the reader to the parser instead of to ``max_tokens``."""
    payload = completion(content='{"chunks": [', finish_reason="length")
    transport = FakeTransport(TransportResult(status=OK, raw=body(payload)))
    result = make_service(transport).complete(ask(schema_id="batch"))
    assert not result.ok
    assert result.failure == "truncated"
    assert result.finish_reason == "length"
    assert result.text == '{"chunks": ['


def test_cut_off_answer_that_parses_is_still_truncated(make_service) -> None:
    payload = completion(content='{"chunks": []}', finish_reason="length")
    transport = FakeTransport(TransportResult(status=OK, raw=body(payload)))
    result = make_service(transport).complete(ask(schema_id="batch"))
    assert not result.ok
    assert result.failure == "truncated"
    assert result.data is None
