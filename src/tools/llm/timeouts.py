"""Socket timeout derived from the shape of the request."""

from __future__ import annotations

from tools.llm.port import Request


class TimeoutPolicy:
    def __init__(
        self,
        *,
        threshold_tokens: int = 8000,
        long_seconds: float = 180.0,
        short_seconds: float = 45.0,
    ) -> None:
        self.threshold_tokens = threshold_tokens
        self.long_seconds = long_seconds
        self.short_seconds = short_seconds

    def seconds_for(self, request: Request) -> float:
        if request.max_tokens > self.threshold_tokens:
            return self.long_seconds
        return self.short_seconds
