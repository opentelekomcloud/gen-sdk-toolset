"""The RST parser port."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from tools.shared.ir import Endpoint


class RstParser(Protocol):
    """Parses an RST endpoint document into an :class:`Endpoint`.

    Style classification happens at the scanner layer *before* the parser
    is invoked, so implementations can assume the input is a Style-A doc
    (Function / URI / Request / Response …). A gating failure during
    parsing (e.g. URI line not found) is signalled by raising
    :class:`ParseFailure`.
    """

    def parse(self, content: str, path: str) -> Endpoint: ...


@runtime_checkable
class RepositoryContextParser(Protocol):
    """Parser that can resolve definitions shared by repository documents."""

    def build_repository_context(self, documents: Mapping[str, str]) -> object: ...

    def parse(
        self, content: str, path: str, *, context: object | None = None
    ) -> Endpoint: ...
