"""Composition root: wire the LLM client for the LiteLLM gateway."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from tools.llm.providers import OpenAICompatibleAdapter
from tools.llm.schemas import SchemaRepository
from tools.llm.service import LLMService, Route
from tools.llm.transport.http import HttpClient
from tools.llm.transport.ratelimit import RateLimiter


def build_llm_service(
    *,
    base_url: str,
    api_key: str,
    models: Iterable[str],
    schemas_root: Path | str | None = None,
    concurrency: int = 8,
    min_interval: float = 0.0,
) -> LLMService:
    """One route per model, all through the same rate-limited HTTP transport.

    The limiter is shared by every model on the gateway: they compete for the
    same endpoint, and a 429 for one is a reason for all of them to wait.
    """
    transport = RateLimiter(
        HttpClient(base_url=base_url, api_key=api_key),
        concurrency=concurrency,
        min_interval=min_interval,
    )
    route = Route(adapter=OpenAICompatibleAdapter(), transport=transport)
    return LLMService(
        routes={model: route for model in models},
        schemas=None if schemas_root is None else SchemaRepository(schemas_root),
    )
