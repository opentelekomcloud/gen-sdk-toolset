"""Post-hoc analytics over a scan result (pure, no scanner/HTTP dependencies).

These functions operate on the already-extracted IR (``Endpoint`` and its
sections) rather than on scanner internals. They are the panel-side home for
derived views over a scan: the status vocabulary and per-document views the
rest builds on (:mod:`quality`), the roll-ups a scan is persisted with
(:mod:`generation`), comparing the documented tables against the parsed
examples (:mod:`validate`) and, on demand, rebuilding the nesting the examples
prove (:mod:`assemble`).
"""

from __future__ import annotations

from .assemble import assemble_nesting_from_examples
from .generation import (
    DocumentAnalytics,
    GenerationAnalytics,
    analyze_document,
    analyze_generation,
    doc_completeness,
    document_from_payload,
    issues_by_code,
)
from .quality import OverallStatus, doc_all_issues
from .validate import example_documentation_issues

__all__ = [
    "DocumentAnalytics",
    "GenerationAnalytics",
    "OverallStatus",
    "analyze_document",
    "analyze_generation",
    "assemble_nesting_from_examples",
    "doc_all_issues",
    "doc_completeness",
    "document_from_payload",
    "example_documentation_issues",
    "issues_by_code",
]
