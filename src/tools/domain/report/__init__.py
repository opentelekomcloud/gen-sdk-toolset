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
everything from ``tools.domain.report`` directly. Counting/roll-up
logic lives in :mod:`.analytics`; the models delegate to it.
"""

from __future__ import annotations

from tools.shared.report.enums import IssueCode, OverallStatus, SectionStatus
from tools.shared.report.keys import (
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

from .aggregates import (
    REPORT_SCHEMA_VERSION,
    OrgScanResult,
    RepoScanResult,
)
from .analytics import QualitySummary
from .document import DocumentScanResult
from .issue import Issue
from .section import ExampleBlock, SectionResult

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
    "Issue",
    "ExampleBlock",
    "SectionResult",
    "DocumentScanResult",
    "RepoScanResult",
    "QualitySummary",
    "OrgScanResult",
]
