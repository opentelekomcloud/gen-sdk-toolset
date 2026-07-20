"""The RST parser port."""

from __future__ import annotations

from typing import Protocol

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
