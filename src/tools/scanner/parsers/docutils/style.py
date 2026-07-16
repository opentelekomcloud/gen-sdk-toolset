"""Doc-style classification for OTC RST API docs.

Determines whether a doc is:

* ``STYLE_A`` — modern OTC layout (Function / URI / Request / Response /
  Example sections). We can extract parameters and examples from it.
* ``S3_COMPATIBLE`` — Object-Storage-Service / S3-style layout with
  ``Request Syntax``, ``Sample Request``, ``Request Elements`` sections
  and HTTP-wire-format code blocks. Recognised but not yet extractable.
* ``NOT_ENDPOINT`` — overview / conceptual pages with no endpoint
  signal. Skipped entirely by the scanner.

Classification is regex-based (no docutils parsing) — it's a cheap
pre-filter that runs before the expensive AST walk.
"""

from __future__ import annotations

import re
from enum import Enum

from .patterns import URI_RE

# S3-style section headings as they appear in OBS docs. We require the
# heading to be a real RST section (text followed by an underline of
# ``-`` / ``=`` / ``~``), not just the phrase appearing in body text.
_S3_HEADINGS = (
    "Request Syntax",
    "Request Elements",
    "Response Syntax",
    "Response Elements",
    "Sample Request",
    "Sample Response",
)
_S3_HEADING_RE = re.compile(
    rf"^({'|'.join(re.escape(h) for h in _S3_HEADINGS)})[ \t]*\n[-=~]+\s*$",
    re.MULTILINE,
)

# Minimum number of distinct S3-style section headings needed before we
# call a doc s3-compatible. Two is enough — these headings don't appear
# in Style-A docs by accident.
_S3_THRESHOLD = 2

# A real "URI" RST section heading (text followed by an underline). Its
# presence means the doc *is* an endpoint doc even when we can't extract a
# method+path line from it — see classify_doc_style.
_URI_HEADING_RE = re.compile(r"^URI[ \t]*\n[-=~^\"'`#*+]+\s*$", re.MULTILINE)

_RST_TITLE_UNDERLINE_CHARS = frozenset("=-~^\"'`#*+")


class DocStyle(str, Enum):
    """Layout classification of an RST doc, mapped to report semantics.

    Mapping to report outcomes:

    * ``STYLE_A``       — modern OTC layout; handed to the parser. (A doc
      with endpoint headings but no extractable URI is still STYLE_A so the
      parser surfaces it as a ``no_uri_match`` gating failure)
    * ``S3_COMPATIBLE`` — OBS/S3 layout; recognised but not yet extractable →
      gating failure ``UNSUPPORTED_DOC_STYLE`` → ``overall_status``
      ``"unsupported"``.
    * ``NOT_ENDPOINT``  — no endpoint signal; represented as a successful
      ``Document`` and excluded from endpoint quality metrics.
    """

    STYLE_A = "style_a"
    S3_COMPATIBLE = "s3_compatible"
    NOT_ENDPOINT = "not_endpoint"


def extract_document_title(content: str) -> str | None:
    """Return the first RST overline-free heading in a document."""
    lines = content.splitlines()
    for title_line, underline_line in zip(lines, lines[1:]):
        if (
            title_line != title_line.lstrip()
            or underline_line != underline_line.lstrip()
        ):
            continue
        title = title_line.rstrip()
        underline = underline_line.rstrip()
        if not title or len(underline) < 3:
            continue
        if len(underline) < len(title):
            continue
        if len(set(underline)) != 1:
            continue
        if underline[0] in _RST_TITLE_UNDERLINE_CHARS:
            return title
    return None


def classify_doc_style(content: str) -> DocStyle:
    """Classify an RST doc as Style-A, S3-compatible, or non-endpoint."""
    s3_markers = len(_S3_HEADING_RE.findall(content))
    if s3_markers >= _S3_THRESHOLD:
        return DocStyle.S3_COMPATIBLE

    if URI_RE.search(content):
        return DocStyle.STYLE_A
    if _URI_HEADING_RE.search(content):
        return DocStyle.STYLE_A

    return DocStyle.NOT_ENDPOINT
