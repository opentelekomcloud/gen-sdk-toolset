"""RST parsing adapters.

The docutils-based Style-A adapter lives in the :mod:`.docutils` subpackage
together with its private helpers.

* :class:`DocutilsParser` — the :class:`tools.scanner.interfaces.RstParser`
  implementation.
* :func:`classify_doc_style` — the cheap regex pre-filter the scanner runs
  before invoking the parser.
"""

from __future__ import annotations

from .docutils.doc_parser import DocutilsParser
from .docutils.style import classify_doc_style, extract_document_title

__all__ = ["DocutilsParser", "classify_doc_style", "extract_document_title"]
