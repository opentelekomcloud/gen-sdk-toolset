"""Provider adapter: our request and result <-> the OpenAI chat-completions format.

The LiteLLM gateway in front of the model speaks this format, so one adapter
covers it. No I/O here: the transport sends, the adapter only builds and reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from tools.llm.port import Request
from tools.llm.transport.base import (
    HTTP_ERROR,
    NETWORK,
    OK,
    RATE_LIMITED,
    TIMEOUT,
    TransportResult,
)

SCHEMA = "json_schema"
JSON_OBJECT = "json_object"
NO_STRUCTURE = "none"
STRUCTURED_MODES = (SCHEMA, JSON_OBJECT, NO_STRUCTURE)


@dataclass(frozen=True)
class ProviderRequest:
    path: str
    body: dict[str, Any]


@dataclass(frozen=True)
class RawResponse:
    text: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""
    ms: int = 0
    failure: str = ""
    error: str = ""
    #: False: the request never reached the endpoint (see ``TransportResult.sent``).
    sent: bool = True
    #: As the endpoint answered; ``0`` - no response at all.
    http_status: int = 0


class OpenAICompatibleAdapter:
    route: str = "openai-compatible"
    path: str = "chat/completions"

    def __init__(self, *, structured_output: str = SCHEMA) -> None:
        if structured_output not in STRUCTURED_MODES:
            raise ValueError(f"unknown structured_output: {structured_output}")
        self.structured_output = structured_output

    def build_request(
        self, request: Request, schema: dict[str, Any] | None
    ) -> ProviderRequest:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "max_tokens": request.max_tokens,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.seed is not None:
            body["seed"] = request.seed
        self._apply_structured_output(body, request, schema)
        return ProviderRequest(path=self.path, body=body)

    def _apply_structured_output(
        self, body: dict[str, Any], request: Request, schema: dict[str, Any] | None
    ) -> None:
        if schema is None or self.structured_output == NO_STRUCTURE:
            return
        if self.structured_output == JSON_OBJECT:
            body["response_format"] = {"type": "json_object"}
            return
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": request.schema_id or "response",
                "strict": bool(request.schema_strict),
                "schema": schema,
            },
        }

    def parse_response(self, result: TransportResult) -> RawResponse:
        if result.status != OK:
            return RawResponse(
                ms=result.elapsed_ms,
                sent=result.sent,
                http_status=result.http_status,
                failure=public_failure(result.status),
                error=self._describe_error(result),
            )

        payload = _decode(result)
        if payload is None:
            return RawResponse(
                ms=result.elapsed_ms,
                http_status=result.http_status,
                failure="invalid_json",
                error=f"body did not parse: {_preview(result)}",
            )

        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        model = payload.get("model")
        model = model if isinstance(model, str) else ""

        def malformed(what: str) -> RawResponse:
            return RawResponse(
                usage=usage,
                model=model,
                ms=result.elapsed_ms,
                http_status=result.http_status,
                failure="invalid_json",
                error=f"unexpected response shape: {what}",
            )

        choices = payload.get("choices")
        if choices is None:
            choices = []
        if not isinstance(choices, list):
            return malformed("choices")
        if not choices:
            return _empty(usage, model, "", result)

        first = choices[0]
        if not isinstance(first, dict):
            return malformed("choices[0]")

        message = first.get("message")
        if message is None:
            message = {}
        if not isinstance(message, dict):
            return malformed("choices[0].message")

        content = message.get("content")
        if content is not None and not isinstance(content, str):
            return malformed("choices[0].message.content")

        finish = first.get("finish_reason")
        finish = finish if isinstance(finish, str) else ""

        if not (content or "").strip():
            return _empty(usage, model, finish, result)

        return RawResponse(
            text=content or "",
            usage=usage,
            model=model,
            finish_reason=finish,
            ms=result.elapsed_ms,
            http_status=result.http_status,
        )

    def _describe_error(self, result: TransportResult) -> str:
        payload = _decode(result)
        detail = ""
        if payload:
            error = payload.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message") or "")
            elif isinstance(error, str):
                detail = error
        parts = [p for p in (result.error, detail) if p]
        if not parts and result.raw:
            parts.append(_preview(result))
        return ": ".join(parts)


def public_failure(transport_status: str) -> str:
    """The port's failure for a transport status that is not ``ok``."""
    return {
        RATE_LIMITED: "rate_limit",
        TIMEOUT: "timeout",
        NETWORK: "network",
        HTTP_ERROR: "http",
    }.get(transport_status, "http")


def _empty(
    usage: dict[str, Any], model: str, finish: str, result: TransportResult
) -> RawResponse:
    return RawResponse(
        usage=usage,
        model=model,
        finish_reason=finish,
        ms=result.elapsed_ms,
        http_status=result.http_status,
        failure="empty",
        error=f"model returned nothing (finish_reason={finish or 'none'})",
    )


def _decode(result: TransportResult) -> dict[str, Any] | None:
    if not result.raw:
        return None
    try:
        text = result.raw.decode(result.charset)
    except (UnicodeDecodeError, LookupError):
        return None
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _preview(result: TransportResult, limit: int = 200) -> str:
    try:
        text = result.raw[:limit].decode(result.charset, errors="replace")
    except LookupError:
        # An unknown codec in Content-Type: errors="replace" does not cover that,
        # and the preview exists to describe a failure, not to raise one.
        text = result.raw[:limit].decode("utf-8", errors="replace")
    return text + ("…" if len(result.raw) > limit else "")
