from typing import Protocol

from tools.domain.report import ParsedDocument


class RstParser(Protocol):
    """Parses an RST endpoint document into a :class:`ParsedDocument`.

    Style classification happens at the scanner layer *before* the parser
    is invoked, so implementations can assume the input is a Style-A doc
    (Function / URI / Request / Response …). A gating failure during
    parsing (e.g. URI line not found) is signalled by raising
    :class:`tools.domain.report.ParseFailure`.
    """

    def parse(self, content: str, path: str) -> ParsedDocument: ...
