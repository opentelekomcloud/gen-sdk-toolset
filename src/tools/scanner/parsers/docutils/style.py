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

from .patterns import S3_HEADING_RE, URI_HEADING_RE, URI_RE
from .types import DocStyle

# Minimum number of distinct S3-style section headings needed before we
# call a doc s3-compatible. Two is enough — these headings don't appear
# in Style-A docs by accident.
_S3_THRESHOLD = 2


def classify_doc_style(content: str) -> DocStyle:
    """Classify an RST doc as Style-A, S3-compatible, or non-endpoint."""
    s3_markers = len({match.lower() for match in S3_HEADING_RE.findall(content)})
    if s3_markers >= _S3_THRESHOLD:
        return DocStyle.S3_COMPATIBLE

    if URI_RE.search(content):
        return DocStyle.STYLE_A
    if URI_HEADING_RE.search(content):
        return DocStyle.STYLE_A

    return DocStyle.NOT_ENDPOINT
