"""Section-heading and table-title classification for Style-A docs.

OTC docs use inconsistent wording for the same logical section
("Request" / "Request Parameters" / "Request Message" / "Requests" all
mean the same thing in practice). The classifier collapses these into
a small, stable set of :class:`SectionKind` values.

Within a section, individual parameter tables also have varying titles
("Path Parameters" / "URI parameter" / "Parameter description", etc.).
The table-title classifier maps them into the canonical section-name
keys consumed by ``DocumentScanResult.sections``.
"""

from __future__ import annotations

import re
from enum import Enum

from tools.domain.report import (
    NESTED_STRUCT,
    SECTION_BODY,
    SECTION_HEADERS,
    SECTION_PATH_PARAMS,
    SECTION_QUERY_PARAMS,
    SECTION_RESPONSE,
)


class SectionKind(str, Enum):
    """High-level role of a top-level section heading inside an RST doc."""

    URI = "uri"
    REQUEST = "request"
    RESPONSE = "response"
    EXAMPLE_REQUEST = "example_request"
    EXAMPLE_RESPONSE = "example_response"
    EXAMPLE_COMBINED = "example_combined"  # singular "Example" / "Examples"
    STATUS_CODES = "status_codes"
    FUNCTION = "function"
    OTHER = "other"


# Maps canonical SectionKind → set of literal heading variants seen in
# the OTC docs. Comparison is case-insensitive on stripped text.
_SECTION_VARIANTS: dict[SectionKind, frozenset[str]] = {
    SectionKind.URI: frozenset({"uri"}),
    SectionKind.REQUEST: frozenset(
        {"request", "request parameters", "request message", "requests"}
    ),
    SectionKind.RESPONSE: frozenset(
        {"response", "response parameters", "response message", "responses"}
    ),
    SectionKind.EXAMPLE_REQUEST: frozenset(
        {"example request", "example requests", "sample request"}
    ),
    SectionKind.EXAMPLE_RESPONSE: frozenset(
        {"example response", "example responses", "sample response"}
    ),
    SectionKind.EXAMPLE_COMBINED: frozenset({"example", "examples"}),
    SectionKind.STATUS_CODES: frozenset(
        {"status code", "status codes", "status code description"}
    ),
    SectionKind.FUNCTION: frozenset({"function", "functions"}),
}


def classify_section_title(title: str) -> SectionKind:
    """Classify a section heading text into a :class:`SectionKind`."""
    key = title.strip().lower()
    for kind, variants in _SECTION_VARIANTS.items():
        if key in variants:
            return kind
    return SectionKind.OTHER


# --------------------------------------------------------------------------- #
# Table title → canonical section key (used as DocumentScanResult.sections key)
# --------------------------------------------------------------------------- #
# Internal marker for status-code tables: recognised so we don't misfile
# them, but they are not parameter tables, so the classifier returns None.
_STATUS_CODES = "status_codes"

# Order matters: more specific patterns first. The classifier walks the
# list and returns the first match.
_TABLE_TITLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Query parameters — must come before the generic path/URI catches so
    # "Query Parameters" tables don't fall through into path_param.
    (re.compile(r"\bquery\s+param", re.IGNORECASE), SECTION_QUERY_PARAMS),
    (
        re.compile(r"\bparameters?\s+in\s+the\s+query", re.IGNORECASE),
        SECTION_QUERY_PARAMS,
    ),
    # URI / path
    (re.compile(r"\bpath\s+param", re.IGNORECASE), SECTION_PATH_PARAMS),
    (re.compile(r"\buri\s+param", re.IGNORECASE), SECTION_PATH_PARAMS),
    # Request header
    (re.compile(r"\brequest\s+header", re.IGNORECASE), SECTION_HEADERS),
    (
        re.compile(r"\bparameters?\s+in\s+the\s+request\s+header", re.IGNORECASE),
        SECTION_HEADERS,
    ),
    (re.compile(r"\bheader\s+param", re.IGNORECASE), SECTION_HEADERS),
    # Request body (must come after header patterns since "request" is
    # ambiguous on its own).
    (re.compile(r"\brequest\s+body", re.IGNORECASE), SECTION_BODY),
    (
        re.compile(r"\bparameters?\s+in\s+the\s+request\s+body", re.IGNORECASE),
        SECTION_BODY,
    ),
    # Response body
    (re.compile(r"\bresponse\s+body", re.IGNORECASE), SECTION_RESPONSE),
    (
        re.compile(r"\bparameters?\s+in\s+the\s+response\s+body", re.IGNORECASE),
        SECTION_RESPONSE,
    ),
    (re.compile(r"\bresponse\s+param", re.IGNORECASE), SECTION_RESPONSE),
    # Generic catches go last
    (re.compile(r"\brequest\s+param", re.IGNORECASE), SECTION_BODY),
    (re.compile(r"\bstatus\s+code", re.IGNORECASE), _STATUS_CODES),
]


def classify_table_title(title: str, *, in_section: SectionKind) -> str | None:
    """Resolve a table title to a canonical section key.

    Returns one of the strings in
    :data:`tools.domain.report.SECTION_NAMES` when the table is a
    primary section table (e.g. path / body / response). Returns
    :data:`tools.domain.report.NESTED_STRUCT` when the title looks like a
    referenced object definition (e.g. ``CreateFirewallOption`` or
    ``metadata``).
    Returns ``None`` for non-parameter tables (status codes, etc.).

    `in_section` provides context: a table in the URI section with a
    generic title defaults to path_params; a table in Response with a
    generic title defaults to response.
    """
    for pattern, key in _TABLE_TITLE_PATTERNS:
        if pattern.search(title):
            if key == _STATUS_CODES:
                return None  # status code tables are not parameter tables
            return key

    # No pattern matched. A generic "Query Parameters"-ish title that
    # somehow reached here must never default to path_params (review
    # item 5); send it to query_params regardless of section.
    if re.search(r"\bquery\b", title, re.IGNORECASE):
        return SECTION_QUERY_PARAMS

    # Fall back on enclosing section. A "Parameter description" table
    # directly under URI is path_params; under Request it's request body;
    # under Response it's response body.
    fallback: dict[SectionKind, str] = {
        SectionKind.URI: SECTION_PATH_PARAMS,
        SectionKind.REQUEST: SECTION_BODY,
        SectionKind.RESPONSE: SECTION_RESPONSE,
    }
    if in_section in fallback:
        # But only if the title looks "parameter-ish" — bare object
        # names like "CreateFirewallOption" are nested struct definitions.
        if _looks_like_parameter_table(title):
            return fallback[in_section]
        return NESTED_STRUCT

    return None


# Keywords that indicate a *primary* parameter table (header / body /
# response) rather than a struct definition. Deliberately excludes "field"
# because OTC titles like "Data structure of the metadata field" describe
# nested struct definitions, not parameter tables.
_PARAM_KEYWORDS = ("parameter", "header")


def _looks_like_parameter_table(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in _PARAM_KEYWORDS)
