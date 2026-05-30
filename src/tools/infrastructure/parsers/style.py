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

from tools.domain.ir import URI_RE


class DocStyle(str, Enum):
    STYLE_A = "style_a"
    S3_COMPATIBLE = "s3_compatible"
    NOT_ENDPOINT = "not_endpoint"


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


def classify_doc_style(content: str) -> DocStyle:
    """Classify an RST doc as Style-A, S3-compatible, or non-endpoint."""
    s3_markers = len(_S3_HEADING_RE.findall(content))
    if s3_markers >= _S3_THRESHOLD:
        return DocStyle.S3_COMPATIBLE

    # Style-A signal: a bare "METHOD /path" line somewhere in the doc.
    if URI_RE.search(content):
        return DocStyle.STYLE_A

    return DocStyle.NOT_ENDPOINT
