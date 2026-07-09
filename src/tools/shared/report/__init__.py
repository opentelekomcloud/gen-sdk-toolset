"""Scan report contracts: enums, canonical keys, and the result forms.

Forms are data-only. Derived analytics (overall status, completeness,
counts) live in ``tools.domain.report.analytics`` until they move to
their final home on the panel side.
"""

from .document import DocumentScanResult
from .enums import IssueCode, OverallStatus, SectionStatus
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
from .repo import RepoScanResult
from .section import ExampleBlock, SectionResult

__all__ = [
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
]