"""Section-heading and table-title classification for Style-A docs.

OTC docs use inconsistent wording for the same logical section
("Request" / "Request Parameters" / "Request Message" / "Requests" all
mean the same thing in practice). The classifier collapses these into
a small, stable set of :class:`SectionKind` values.

Within a section, individual parameter tables also have varying titles
("Path Parameters" / "URI parameter" / "Parameter description", etc.).
The table-title classifier maps them into canonical section names.
"""

from __future__ import annotations

import re
from enum import Enum

from tools.shared.ir import SectionName


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


class TableTarget(str, Enum):
    """Internal routing targets that are not endpoint sections."""

    NESTED_STRUCT = "nested_struct"
    GENERIC_REQUEST = "generic_request"
    INTENTIONALLY_IGNORED = "intentionally_ignored"
    UNMAPPED = "unmapped"


# Maps canonical SectionKind → set of literal heading variants seen in
# the OTC docs. Comparison is case-insensitive on stripped text.
_SECTION_VARIANTS: dict[SectionKind, frozenset[str]] = {
    SectionKind.URI: frozenset({"uri"}),
    SectionKind.REQUEST: frozenset(
        {"request", "request parameters", "request message", "requests"}
    ),
    SectionKind.RESPONSE: frozenset(
        {
            "response",
            "response parameters",
            "response message",
            "response messages",
            "responses",
        }
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
# Table title → canonical section name
# --------------------------------------------------------------------------- #
# Order matters: more specific patterns first. The classifier walks the
# list and returns the first match.
_TABLE_TITLE_PATTERNS: list[tuple[re.Pattern[str], SectionName | TableTarget]] = [
    # Query parameters — must come before the generic path/URI catches so
    # "Query Parameters" tables don't fall through into path_param.
    (re.compile(r"\bquery\s+param", re.IGNORECASE), SectionName.QUERY_PARAMS),
    (
        re.compile(r"\bparameters?\s+in\s+the\s+query", re.IGNORECASE),
        SectionName.QUERY_PARAMS,
    ),
    # URI / path
    (re.compile(r"\bpath\s+param", re.IGNORECASE), SectionName.PATH_PARAMS),
    (re.compile(r"\buri\s+param", re.IGNORECASE), SectionName.PATH_PARAMS),
    # Request header. (The broad "request header" catch already matches
    # titles like "Parameters in the request header", so no separate pattern
    # for that phrasing is needed.)
    (re.compile(r"\brequest\s+header", re.IGNORECASE), SectionName.HEADERS),
    (re.compile(r"\bheader\s+param", re.IGNORECASE), SectionName.HEADERS),
    # Request body (must come after header patterns since "request" is
    # ambiguous on its own).
    (re.compile(r"\brequest\s+body", re.IGNORECASE), SectionName.BODY),
    # Response body
    (re.compile(r"\bresponse\s+body", re.IGNORECASE), SectionName.RESPONSE),
    (re.compile(r"\bresponse\s+param", re.IGNORECASE), SectionName.RESPONSE),
    # Generic catches go last
    (re.compile(r"\brequest\s+param", re.IGNORECASE), TableTarget.GENERIC_REQUEST),
]

_STATUS_CODE_TABLE_RE = re.compile(r"\bstatus\s+code", re.IGNORECASE)
_NESTED_LABEL_PATTERNS = (
    re.compile(
        r"^data\s+structure\s+description\s+of\s+(.+?)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:table\s+\d+\s+)?description\s+of\s+(?:the\s+)?field\s+(.+?)$",
        re.IGNORECASE,
    ),
)

_DEFAULT_TABLE_SECTIONS = {
    SectionKind.URI: SectionName.PATH_PARAMS,
    SectionKind.REQUEST: SectionName.BODY,
    SectionKind.RESPONSE: SectionName.RESPONSE,
}


def classify_table_title(
    title: str, *, in_section: SectionKind
) -> SectionName | TableTarget:
    """Resolve a table title to a canonical section key.

    Returns a canonical ``SectionName`` for primary parameter tables and
    ``TableTarget.NESTED_STRUCT`` for referenced object definitions.
    Returns ``TableTarget.INTENTIONALLY_IGNORED`` for known non-parameter
    tables and ``TableTarget.UNMAPPED`` when no safe route can be inferred.

    `in_section` provides context: a table in the URI section with a
    generic title defaults to path_params; a table in Response with a
    generic title defaults to response.
    """
    if _STATUS_CODE_TABLE_RE.search(title):
        return TableTarget.INTENTIONALLY_IGNORED

    for pattern, key in _TABLE_TITLE_PATTERNS:
        if pattern.search(title):
            return key

    # No pattern matched. A generic "Query Parameters"-ish title that
    # somehow reached here must never default to path_params (review
    # item 5); send it to query_params regardless of section.
    if re.search(r"\bquery\b", title, re.IGNORECASE):
        return SectionName.QUERY_PARAMS

    # Fall back on enclosing section. A "Parameter description" table
    # directly under URI is path_params; under Request it's request body;
    # under Response it's response body.
    if in_section in _DEFAULT_TABLE_SECTIONS:
        # But only if the title looks "parameter-ish" — bare object
        # names like "CreateFirewallOption" are nested struct definitions.
        if _looks_like_parameter_table(title):
            if in_section is SectionKind.REQUEST:
                return TableTarget.GENERIC_REQUEST
            return _DEFAULT_TABLE_SECTIONS[in_section]
        if title:
            return TableTarget.NESTED_STRUCT
        return TableTarget.UNMAPPED

    return TableTarget.UNMAPPED


def default_table_section(kind: SectionKind) -> SectionName:
    """Return the canonical section that owns diagnostics for a table."""
    return _DEFAULT_TABLE_SECTIONS[kind]


def nested_parent_name(title: str) -> str | None:
    cleaned = title.strip()
    for pattern in _NESTED_LABEL_PATTERNS:
        match = pattern.match(cleaned)
        if match:
            return match.group(1).strip()
    return None


# Keywords that indicate a *primary* parameter table (header / body /
# response) rather than a struct definition. Deliberately excludes "field"
# because OTC titles like "Data structure of the metadata field" describe
# nested struct definitions, not parameter tables.
_PARAM_KEYWORDS = ("parameter", "header")


def _looks_like_parameter_table(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in _PARAM_KEYWORDS)
