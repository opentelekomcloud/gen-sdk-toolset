"""Quality-report scan result models.

* **Gating vs content.** Parsing a doc has prerequisite steps (fetch the
  file, recognise it as an endpoint doc, locate the URI) and content
  steps (extract path / query / body / response parameters, examples,
  nested objects). A failure in a gating step makes the doc unusable;
  a failure in one content section is independent of the others, so the
  doc can still be *partially* useful.
* **Per-section result + structured issues.** Every content section
  carries its own :class:`SectionStatus`, structured :class:`Issue`
  entries, the actually-extracted data (``parameters`` / ``examples``),
  and field-level metrics. The data and the metrics travel together —
  no parallel storage to keep in sync.

The org-wide report (:class:`OrgScanResult`) carries a derived
:class:`QualitySummary` so a single JSON dump answers "how is the doc
set doing across all repos".

This package re-exports its public names so callers can keep importing
everything from ``tools.domain.report`` directly. ``ParsedDocument`` /
``ParseFailure`` are the parser *port's* contract and live next to the
port in :mod:`tools.domain.interfaces.parser`; they are re-exported here
for backwards compatibility.
"""

from __future__ import annotations

from .aggregates import (
    REPORT_SCHEMA_VERSION,
    OrgScanResult,
    QualitySummary,
    RepoScanResult,
)
from .document import DocumentScanResult
from .enums import DocStyle, IssueCode, OverallStatus, SectionStatus
from .issue import Issue
from .keys import (
    NESTED_STRUCT,
    SECTION_BODY,
    SECTION_EXAMPLE_REQUEST,
    SECTION_EXAMPLE_RESPONSE,
    SECTION_HEADERS,
    SECTION_NAMES,
    SECTION_NESTED_OBJECTS,
    SECTION_PATH_PARAMS,
    SECTION_QUERY_PARAMS,
    SECTION_RESPONSE,
    UNVERSIONED_KEY,
)
from .section import ExampleBlock, SectionResult

# `ParsedDocument` / `ParseFailure` live in tools.domain.interfaces.parser
# (the parser port's contract). They are re-exported here for backwards
# compatibility, but *lazily* via PEP 562: importing them eagerly would form
# a cycle, because interfaces.parser imports the report submodules above.
# Deferring the import until first access breaks that cycle regardless of
# which module is imported first.
_LAZY_REEXPORTS = frozenset({"ParsedDocument", "ParseFailure"})


def __getattr__(name: str):
    if name in _LAZY_REEXPORTS:
        from tools.domain.interfaces import parser

        return getattr(parser, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "SECTION_NAMES",
    "SECTION_PATH_PARAMS",
    "SECTION_QUERY_PARAMS",
    "SECTION_HEADERS",
    "SECTION_BODY",
    "SECTION_RESPONSE",
    "SECTION_EXAMPLE_REQUEST",
    "SECTION_EXAMPLE_RESPONSE",
    "SECTION_NESTED_OBJECTS",
    "NESTED_STRUCT",
    "UNVERSIONED_KEY",
    "SectionStatus",
    "OverallStatus",
    "IssueCode",
    "DocStyle",
    "Issue",
    "ExampleBlock",
    "SectionResult",
    "DocumentScanResult",
    "RepoScanResult",
    "QualitySummary",
    "OrgScanResult",
    "ParsedDocument",
    "ParseFailure",
]
