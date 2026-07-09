"""The RST parser port and its contract types.

``ParsedDocument`` and ``ParseFailure`` are the parser port's contract, so
they live here next to the :class:`RstParser` Protocol rather than in the
report models. They are re-exported from ``tools.domain.report`` for
backwards compatibility.

Imports reach into the report *submodules* (``report.section`` etc.) rather
than the ``report`` package root so that ``report/__init__`` can re-export
these names without creating an import cycle.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from tools.shared.ir import HttpMethod
from tools.domain.report.enums import IssueCode
from tools.domain.report.issue import Issue
from tools.domain.report.section import SectionResult


class ParsedDocument(BaseModel):
    """Parser output for one Style-A doc.

    The parser is style-agnostic at its public surface: callers pass an
    RST string, get back this object on success or a ``ParseFailure``
    exception on a gating problem. Style classification happens at the
    scanner layer, *before* the parser is invoked.
    """

    method: HttpMethod
    uri: str
    title: str | None = None
    api_version: str | None = None
    sections: dict[str, SectionResult] = Field(default_factory=dict)


class ParseFailure(Exception):
    """Raised by the parser when a gating step fails (e.g. no URI in doc).

    Caught at the scanner layer and converted into
    :attr:`DocumentScanResult.failure_reason`.
    """

    def __init__(self, code: IssueCode, details: str | None = None):
        self.issue = Issue(code=code, details=details)
        super().__init__(f"{code.value}" + (f": {details}" if details else ""))


class RstParser(Protocol):
    """Parses an RST endpoint document into a :class:`ParsedDocument`.

    Style classification happens at the scanner layer *before* the parser
    is invoked, so implementations can assume the input is a Style-A doc
    (Function / URI / Request / Response …). A gating failure during
    parsing (e.g. URI line not found) is signalled by raising
    :class:`ParseFailure`.
    """

    def parse(self, content: str, path: str) -> ParsedDocument: ...
