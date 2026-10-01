"""The LLM port and the composition root that assembles it.

That the port imports none of its implementations is pinned by the import-linter
contract "the llm port does not depend on its implementations"; these tests pin
what the contract cannot see - the vocabulary, the shapes, the wiring.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from tools.llm import FAILURES, LLM, Request, Result, build_llm_service
from tools.llm.providers import OpenAICompatibleAdapter
from tools.llm.schemas import SchemaRepository
from tools.llm.transport.http import HttpClient
from tools.llm.transport.ratelimit import RateLimiter

LLM_DIR = Path(__file__).resolve().parents[1] / "src" / "tools" / "llm"


# --- the port --- #


def test_port_defines_no_exception_type():
    """Failures are values: an exception class here would invite raising them."""
    tree = ast.parse((LLM_DIR / "port.py").read_text(encoding="utf-8"))
    raising = [
        c.name
        for c in ast.walk(tree)
        if isinstance(c, ast.ClassDef)
        for b in c.bases
        if isinstance(b, ast.Name) and b.id.endswith(("Error", "Exception"))
    ]
    assert raising == []


def test_failures_have_no_duplicates():
    assert len(FAILURES) == len(set(FAILURES))


@pytest.mark.parametrize(
    "cause",
    [
        "config",
        "rate_limit",
        "timeout",
        "network",
        "http",
        "empty",
        "truncated",
        "invalid_json",
        "schema_invalid",
    ],
)
def test_failures_cover_every_layer(cause):
    assert cause in FAILURES


def test_success_is_the_empty_string():
    assert "" not in FAILURES
    assert Result(ok=True).failure == ""


# --- request --- #


def test_request_says_what_to_ask_not_how_to_execute():
    fields = {f.name for f in dataclasses.fields(Request)}
    for forbidden in ("use_cache", "timeout", "retries", "attempts", "cache"):
        assert forbidden not in fields


def test_request_is_frozen():
    request = Request(model="m", system="s", user="u", purpose="p")
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(request, "model", "other")


def test_request_temperature_defaults_to_the_provider_default_explicitly():
    assert Request(model="m", system="s", user="u", purpose="p").temperature is None


# --- result --- #


def test_result_carries_llm_facts_for_provenance():
    fields = {f.name for f in dataclasses.fields(Result)}
    for name in (
        "model",
        "route",
        "purpose",
        "usage",
        "finish_reason",
        "sent",
        "http_status",
        "ms",
        "schema_sha",
        "requested_at",
    ):
        assert name in fields


def test_result_usage_default_is_not_shared_between_results():
    first, second = Result(ok=True), Result(ok=True)
    first.usage["tokens"] = 1
    assert second.usage == {}


def test_result_has_no_unwrap():
    assert not hasattr(Result(ok=True), "unwrap")


def test_any_object_with_complete_satisfies_the_port():
    class Fake:
        def complete(self, request: Request) -> Result:
            return Result(ok=True, text="ok", purpose=request.purpose)

    service: LLM = Fake()
    result = service.complete(Request(model="m", system="s", user="u", purpose="p"))
    assert result.text == "ok"
    assert result.purpose == "p"


# --- composition root --- #


def _build(**overrides):
    return build_llm_service(
        base_url="http://gateway.test/v1/",
        api_key="k",
        models=["a", "b"],
        **overrides,
    )


def test_stack_is_a_limiter_over_http_to_the_given_gateway():
    route = _build()._routes["a"]
    assert isinstance(route.transport, RateLimiter)
    assert isinstance(route.transport._inner, HttpClient)
    assert route.transport._inner.base_url == "http://gateway.test/v1"
    assert isinstance(route.adapter, OpenAICompatibleAdapter)


def test_every_model_shares_one_limiter():
    service = _build()
    assert set(service._routes) == {"a", "b"}
    assert service._routes["a"].transport is service._routes["b"].transport


def test_no_schema_repository_without_a_schemas_root():
    assert _build()._schemas is None


def test_schemas_root_gives_a_repository_there(tmp_path):
    schemas = _build(schemas_root=tmp_path)._schemas
    assert isinstance(schemas, SchemaRepository)
    assert schemas.root == tmp_path


def test_unknown_model_is_a_config_failure_that_was_never_sent():
    result = _build().complete(
        Request(model="not-configured", system="s", user="u", purpose="p")
    )
    assert result.ok is False
    assert result.failure == "config"
    assert result.sent is False
    assert "not-configured" in result.error
    assert result.purpose == "p"


def test_schema_asked_without_a_repository_is_a_config_failure():
    result = _build().complete(
        Request(model="a", system="s", user="u", purpose="p", schema_id="refine")
    )
    assert result.failure == "config"
    assert result.sent is False
    assert result.route == "openai-compatible"
