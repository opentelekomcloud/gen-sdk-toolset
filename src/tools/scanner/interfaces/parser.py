"""The RST parser port and its contract types.

``ParsedDocument`` is the parser port's contract, so it lives here next
to the :class:`RstParser` Protocol. ``ParseFailure`` is part of the
shared exception hierarchy (``tools.shared.exceptions``) and is
re-exported from this package for convenience.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from tools.shared.ir import Endpoint
from tools.shared.report.section import SectionScanResult


class ParsedDocument(BaseModel):
    """Parser output for one Style-A doc.

    The parser is style-agnostic at its public surface: callers pass an
    RST string, get back this object on success or a ``ParseFailure``
    exception on a gating problem. Style classification happens at the
    scanner layer, *before* the parser is invoked.
    """

    endpoint: Endpoint
    section_results: list[SectionScanResult] = Field(default_factory=list)


class RstParser(Protocol):
    """Parses an RST endpoint document into a :class:`ParsedDocument`.

    Style classification happens at the scanner layer *before* the parser
    is invoked, so implementations can assume the input is a Style-A doc
    (Function / URI / Request / Response …). A gating failure during
    parsing (e.g. URI line not found) is signalled by raising
    :class:`ParseFailure`.
    """

    def parse(self, content: str, path: str) -> ParsedDocument: ...
