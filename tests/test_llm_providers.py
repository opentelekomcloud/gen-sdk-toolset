"""OpenAI-compatible provider adapter: request building and response reading.

The adapter does no I/O: it turns a ``Request`` into a chat-completions body and
a ``TransportResult`` into a ``RawResponse``, naming every failure from the
port's vocabulary rather than raising.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tools.llm.port import FAILURES, Request
from tools.llm.providers import (
    JSON_OBJECT,
    NO_STRUCTURE,
    OpenAICompatibleAdapter,
    RawResponse,
    public_failure,
)
from tools.llm.transport.base import (
    HTTP_ERROR,
    NETWORK,
    OK,
    RATE_LIMITED,
    TIMEOUT,
    TransportResult,
)

PROVIDERS_FILE = (
    Path(__file__).resolve().parents[1] / "src" / "tools" / "llm" / "providers.py"
)

SCHEMA_BODY = {"type": "object", "properties": {"chunks": {"type": "array"}}}


def ask(**overrides) -> Request:
    return Request(
        **{
            "model": "qwen3.6-35b",
            "system": "system prompt",
            "user": "user text",
            "purpose": "refine",
            **overrides,
        }
    )


def answered(
    payload,
    *,
    status: str = OK,
    http_status: int = 200,
    raw: bytes | None = None,
    headers: dict[str, str] | None = None,
    error: str = "",
) -> TransportResult:
    if raw is None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return TransportResult(
        status=status,
        raw=raw,
        http_status=http_status,
        headers=headers or {},
        elapsed_ms=1234,
        error=error,
    )


def completion(
    content="generated code",
    finish="stop",
    usage=None,
    model="qwen3.6-35b",
):
    return {
        "model": model,
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish,
            }
        ],
        "usage": usage
        if usage is not None
        else {"prompt_tokens": 10, "completion_tokens": 5},
    }


def parse(payload) -> RawResponse:
    return OpenAICompatibleAdapter().parse_response(answered(payload))


# --- no I/O --- #


def test_providers_do_not_import_transport_or_network():
    names: list[str] = []
    for node in ast.walk(ast.parse(PROVIDERS_FILE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    bad = [
        n
        for n in names
        if n.startswith(("urllib", "http", "socket", "requests", "httpx"))
        or n.endswith("transport.http")
        or n.endswith("transport.ratelimit")
    ]
    assert bad == []


# --- building the request --- #


def test_request_carries_messages_model_and_ceiling():
    body = OpenAICompatibleAdapter().build_request(ask(max_tokens=9000), None).body
    assert body["model"] == "qwen3.6-35b"
    assert body["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user text"},
    ]
    assert body["max_tokens"] == 9000


def test_request_path_is_chat_completions():
    assert OpenAICompatibleAdapter().build_request(ask(), None).path == (
        "chat/completions"
    )


def test_route_is_named_after_the_api_not_the_model():
    assert OpenAICompatibleAdapter().route == "openai-compatible"


def test_request_body_carries_no_reasoning_or_cost_switches():
    """The gateway decides thinking; an unverified switch would be a 400 per call."""
    body = OpenAICompatibleAdapter().build_request(ask(), None).body
    assert "reasoning" not in body
    assert "usage" not in body


def test_temperature_and_seed_are_omitted_unless_set():
    body = OpenAICompatibleAdapter().build_request(ask(), None).body
    assert "temperature" not in body
    assert "seed" not in body


def test_temperature_and_seed_are_passed_when_set():
    body = (
        OpenAICompatibleAdapter().build_request(ask(temperature=0.2, seed=7), None).body
    )
    assert body["temperature"] == 0.2
    assert body["seed"] == 7


def test_zero_temperature_is_sent_not_dropped():
    body = OpenAICompatibleAdapter().build_request(ask(temperature=0.0), None).body
    assert body["temperature"] == 0.0


# --- structured output --- #


def test_schema_travels_inside_the_body():
    body = (
        OpenAICompatibleAdapter()
        .build_request(ask(schema_id="refine-batch"), SCHEMA_BODY)
        .body
    )
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "refine-batch"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA_BODY
    assert body["response_format"]["json_schema"]["strict"] is True


def test_no_schema_means_no_response_format():
    body = OpenAICompatibleAdapter().build_request(ask(), None).body
    assert "response_format" not in body


def test_schema_strict_false_is_passed_through():
    body = (
        OpenAICompatibleAdapter()
        .build_request(ask(schema_id="s", schema_strict=False), SCHEMA_BODY)
        .body
    )
    assert body["response_format"]["json_schema"]["strict"] is False


def test_json_object_mode_asks_for_any_object():
    body = (
        OpenAICompatibleAdapter(structured_output=JSON_OBJECT)
        .build_request(ask(schema_id="s"), SCHEMA_BODY)
        .body
    )
    assert body["response_format"] == {"type": "json_object"}


def test_none_mode_sends_no_response_format():
    body = (
        OpenAICompatibleAdapter(structured_output=NO_STRUCTURE)
        .build_request(ask(schema_id="s"), SCHEMA_BODY)
        .body
    )
    assert "response_format" not in body


def test_unknown_structured_output_mode_is_refused_loudly():
    with pytest.raises(ValueError):
        OpenAICompatibleAdapter(structured_output="somehow")


# --- reading the response --- #


def test_response_gives_text_usage_and_finish_reason():
    raw = parse(completion())
    assert raw.failure == ""
    assert raw.text == "generated code"
    assert raw.usage["completion_tokens"] == 5
    assert raw.finish_reason == "stop"
    assert raw.model == "qwen3.6-35b"
    assert raw.ms == 1234


def test_empty_content_is_named_empty_with_the_finish_reason():
    raw = parse(completion(content="", finish="length"))
    assert raw.failure == "empty"
    assert "length" in raw.error
    assert raw.usage["prompt_tokens"] == 10


def test_whitespace_only_content_is_also_empty():
    assert parse(completion(content="   \n ")).failure == "empty"


def test_empty_choices_list_is_empty():
    assert parse({"model": "m", "choices": []}).failure == "empty"


def test_absent_choices_key_is_empty():
    assert parse({"model": "m"}).failure == "empty"


def test_unparsable_body_on_a_successful_http_is_invalid_json():
    raw = OpenAICompatibleAdapter().parse_response(
        answered(None, raw=b"<html>502</html>")
    )
    assert raw.failure == "invalid_json"
    assert "502" in raw.error


def test_non_ascii_text_survives():
    assert parse(completion(content="naïve café — 東京")).text == "naïve café — 東京"


def test_charset_from_the_content_type_is_honoured():
    raw = json.dumps(completion(content="Grüße"), ensure_ascii=False).encode("latin-1")
    result = OpenAICompatibleAdapter().parse_response(
        answered(
            None,
            raw=raw,
            headers={"Content-Type": "application/json; charset=latin-1"},
        )
    )
    assert result.failure == ""
    assert result.text == "Grüße"


# --- malformed envelopes --- #
# The port promises that a malformed answer is a named failure, never an exception.


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": [None]},
        {"choices": "oops"},
        {"choices": {"a": 1}},
        {"choices": [{"message": []}]},
        {"choices": [{"message": {"content": [{"type": "text", "text": "x"}]}}]},
        {"choices": [{"message": {"content": 42}}]},
    ],
    ids=[
        "null_choice",
        "choices_is_a_string",
        "choices_is_a_dict",
        "message_is_a_list",
        "content_is_a_list_of_parts",
        "content_is_a_number",
    ],
)
def test_malformed_envelope_is_invalid_json(payload):
    raw = parse(payload)
    assert raw.failure in FAILURES
    assert raw.failure == "invalid_json"


def test_missing_message_is_empty_not_a_crash():
    raw = parse({"choices": [{"finish_reason": "stop"}]})
    assert raw.failure in FAILURES
    assert raw.failure == "empty"


def test_wrong_usage_type_does_not_kill_a_good_answer():
    payload = completion()
    payload["usage"] = "oops"
    raw = parse(payload)
    assert raw.failure == ""
    assert raw.text == "generated code"
    assert raw.usage == {}


def test_wrong_model_type_does_not_kill_a_good_answer():
    payload = completion()
    payload["model"] = 7
    raw = parse(payload)
    assert raw.failure == ""
    assert raw.model == ""


def test_wrong_finish_reason_type_is_ignored():
    payload = completion(finish=None)
    payload["choices"][0]["finish_reason"] = ["stop"]
    raw = parse(payload)
    assert raw.failure == ""
    assert raw.finish_reason == ""


def test_usage_and_model_survive_a_malformed_envelope():
    raw = parse({"model": "m", "usage": {"prompt_tokens": 3}, "choices": [None]})
    assert raw.failure == "invalid_json"
    assert raw.usage == {"prompt_tokens": 3}
    assert raw.model == "m"


def test_top_level_array_is_invalid_json():
    raw = OpenAICompatibleAdapter().parse_response(answered(None, raw=b"[1, 2]"))
    assert raw.failure == "invalid_json"


# --- failure naming --- #


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (RATE_LIMITED, "rate_limit"),
        (TIMEOUT, "timeout"),
        (NETWORK, "network"),
        (HTTP_ERROR, "http"),
    ],
)
def test_transport_statuses_become_public_failures(status, expected):
    raw = OpenAICompatibleAdapter().parse_response(
        answered(None, status=status, raw=b"")
    )
    assert raw.failure == expected
    assert raw.failure in FAILURES


def test_unknown_transport_status_is_named_http():
    assert public_failure("something-new") == "http"


def test_transport_failure_keeps_sent_and_status():
    result = TransportResult(status=NETWORK, sent=False, error="refused")
    raw = OpenAICompatibleAdapter().parse_response(result)
    assert raw.failure == "network"
    assert raw.sent is False
    assert raw.http_status == 0
    assert raw.error == "refused"


def test_provider_explanation_is_kept():
    body = {"error": {"message": "model not found: qwen3.6-35x"}}
    raw = OpenAICompatibleAdapter().parse_response(
        answered(body, status=HTTP_ERROR, http_status=400, error="HTTP 400")
    )
    assert raw.failure == "http"
    assert raw.http_status == 400
    assert "HTTP 400" in raw.error
    assert "qwen3.6-35x" in raw.error


def test_string_error_field_is_kept():
    raw = OpenAICompatibleAdapter().parse_response(
        answered(
            {"error": "quota exceeded"},
            status=HTTP_ERROR,
            http_status=403,
            error="HTTP 403",
        )
    )
    assert raw.error == "HTTP 403: quota exceeded"


def test_unreadable_error_body_still_gives_something():
    raw = OpenAICompatibleAdapter().parse_response(
        answered(None, status=HTTP_ERROR, http_status=502, raw=b"<h1>Bad Gateway</h1>")
    )
    assert "Bad Gateway" in raw.error


def test_long_unreadable_body_is_previewed_not_dumped():
    raw = OpenAICompatibleAdapter().parse_response(answered(None, raw=b"x" * 500))
    assert raw.failure == "invalid_json"
    assert raw.error.endswith("…")
    assert len(raw.error) < 300


def test_error_field_of_another_type_leaves_the_transport_error_alone():
    raw = OpenAICompatibleAdapter().parse_response(
        answered({"error": 17}, status=HTTP_ERROR, http_status=500, error="HTTP 500")
    )
    assert raw.error == "HTTP 500"


@pytest.mark.parametrize(
    ("raw_body", "content_type"),
    [
        (b"\xff\xfe{}", "application/json; charset=utf-8"),
        (b"{}", "application/json; charset=no-such-codec"),
    ],
    ids=["undecodable_bytes", "unknown_charset"],
)
def test_body_that_cannot_be_decoded_is_invalid_json(raw_body, content_type):
    raw = OpenAICompatibleAdapter().parse_response(
        answered(None, raw=raw_body, headers={"Content-Type": content_type})
    )
    assert raw.failure == "invalid_json"
