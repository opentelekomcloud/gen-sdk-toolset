"""Orchestration of one call: the order of the steps, nothing else."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from tools.llm.parsing import Parser
from tools.llm.port import Request, Result
from tools.llm.providers import OpenAICompatibleAdapter
from tools.llm.schemas import SchemaNotFound, SchemaRepository
from tools.llm.timeouts import TimeoutPolicy
from tools.llm.transport.base import Transport


@dataclass(frozen=True)
class Route:
    adapter: OpenAICompatibleAdapter
    transport: Transport


class LLMService:
    def __init__(
        self,
        *,
        routes: Mapping[str, Route],
        schemas: SchemaRepository | None = None,
        timeouts: TimeoutPolicy | None = None,
        parser: Parser | None = None,
    ) -> None:
        self._routes = dict(routes)
        self._schemas = schemas
        self._timeouts = timeouts or TimeoutPolicy()
        self._parser = parser or Parser()

    def complete(self, request: Request) -> Result:
        started = time.monotonic()
        requested_at = datetime.now(UTC).isoformat()

        route = self._routes.get(request.model)
        if route is None:
            return _config_failure(
                request, "", f"unknown model: {request.model}", requested_at, started
            )

        schema: dict[str, Any] | None = None
        schema_sha = ""
        if request.schema_id:
            if self._schemas is None:
                return _config_failure(
                    request,
                    route.adapter.route,
                    "schema requested but no repository is configured",
                    requested_at,
                    started,
                )
            try:
                loaded = self._schemas.get(request.schema_id)
            except SchemaNotFound as error:
                return _config_failure(
                    request, route.adapter.route, str(error), requested_at, started
                )
            schema, schema_sha = loaded.body, loaded.sha

        provider_request = route.adapter.build_request(request, schema)
        sent = route.transport.send(
            provider_request.path,
            provider_request.body,
            timeout=self._timeouts.seconds_for(request),
        )
        raw = route.adapter.parse_response(sent)
        common: dict[str, Any] = dict(
            model=request.model,
            route=route.adapter.route,
            purpose=request.purpose,
            usage=dict(raw.usage),
            finish_reason=raw.finish_reason,
            sent=raw.sent,
            http_status=raw.http_status,
            ms=raw.ms or _elapsed(started),
            schema_sha=schema_sha,
            requested_at=requested_at,
        )

        if raw.failure:
            return Result(ok=False, failure=raw.failure, error=raw.error, **common)

        # A reply cut at max_tokens is not an answer. Without a schema nothing
        # else would notice: the cut-off text would reach the caller as if the
        # missing part had never been asked for.
        if raw.finish_reason == "length":
            return Result(
                ok=False,
                text=raw.text,
                failure="truncated",
                error=f"cut at max_tokens={request.max_tokens}",
                **common,
            )

        data = None
        if schema is not None:
            parsed = self._parser.parse_and_validate(raw.text, schema)
            if parsed.failure:
                return Result(
                    ok=False,
                    text=raw.text,
                    data=parsed.data,
                    failure=parsed.failure,
                    error=parsed.error,
                    **common,
                )
            data = parsed.data

        return Result(ok=True, text=raw.text, data=data, **common)


def _config_failure(
    request: Request, route: str, error: str, requested_at: str, started: float
) -> Result:
    # Decided here, before any transport: nothing was sent.
    return Result(
        ok=False,
        failure="config",
        error=error,
        model=request.model,
        route=route,
        purpose=request.purpose,
        ms=_elapsed(started),
        requested_at=requested_at,
        sent=False,
    )


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
