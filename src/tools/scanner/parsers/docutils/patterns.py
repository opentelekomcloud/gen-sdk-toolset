"""Text-recognition regexes for OTC RST docs."""

from __future__ import annotations

import re

from tools.shared.ir import HttpMethod, SectionName

from .types import SectionKind, TableTarget

HTTP_METHODS_PATTERN = "|".join(m.value for m in HttpMethod)

# Matches "POST /path" or "POST https://host/path"
URI_RE = re.compile(
    rf"^\s*({HTTP_METHODS_PATTERN})\s+(?:https?://[^/\s]+)?(/\S*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Matches "{project_id}"
URI_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")

# Matches "POST /path\n" prefix in example blocks
EXAMPLE_HTTP_PREFIX_RE = re.compile(
    rf"^\s*({HTTP_METHODS_PATTERN})\s+(?:https?://[^/\s]+)?/\S+\s*\n",
    re.IGNORECASE,
)

# Extracts version from URI or path (e.g., "v3.1")
API_VERSION_RE = re.compile(r"/(v\d+(?:\.\d+)?)(?:/|$)", re.IGNORECASE)

# Sphinx role targets, e.g., "Text <anchor>"
SPHINX_ANCHOR_RE = re.compile(r"<([^>]+)>\s*$")
SPHINX_LABEL_RE = re.compile(r"\s*<[^>]+>\s*$")

# Explicit field details sentence, e.g. "details about the project_id field"
FIELD_DETAILS_RE = re.compile(
    r"\bdetails\s+about\s+the\s+([A-Za-z0-9_.-]+)\s+field\b",
    re.IGNORECASE,
)

SECTION_VARIANTS: dict[SectionKind, frozenset[str]] = {
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

TABLE_TITLE_PATTERNS: list[tuple[re.Pattern[str], SectionName | TableTarget]] = [
    (re.compile(r"\bstatus\s+code", re.IGNORECASE), TableTarget.INTENTIONALLY_IGNORED),
    (re.compile(r"\bquery\s+param", re.IGNORECASE), SectionName.QUERY_PARAMS),
    (
        re.compile(r"\bparameters?\s+in\s+the\s+query", re.IGNORECASE),
        SectionName.QUERY_PARAMS,
    ),
    (re.compile(r"\bpath\s+param", re.IGNORECASE), SectionName.PATH_PARAMS),
    (re.compile(r"\buri\s+param", re.IGNORECASE), SectionName.PATH_PARAMS),
    (re.compile(r"\brequest\s+header", re.IGNORECASE), SectionName.HEADERS),
    (re.compile(r"\bheader\s+param", re.IGNORECASE), SectionName.HEADERS),
    (re.compile(r"\brequest\s+body", re.IGNORECASE), SectionName.BODY),
    (re.compile(r"\bresponse\s+body", re.IGNORECASE), SectionName.RESPONSE),
    (re.compile(r"\bresponse\s+param", re.IGNORECASE), SectionName.RESPONSE),
    (re.compile(r"\brequest\s+param", re.IGNORECASE), TableTarget.GENERIC_REQUEST),
    (re.compile(r"\bquery\b", re.IGNORECASE), SectionName.QUERY_PARAMS),
]

NESTED_LABEL_PATTERNS = (
    re.compile(r"^data\s+structure\s+description\s+of\s+(.+?)$", re.IGNORECASE),
    re.compile(r"^(?:table\s+\d+\s+)?description\s+of\s+(?:the\s+)?field\s+(.+?)$", re.IGNORECASE),
)

PARAM_KEYWORDS = ("parameter", "header")

S3_HEADINGS = (
    "Request Syntax",
    "Request Elements",
    "Response Syntax",
    "Response Elements",
    "Sample Request",
    "Sample Response",
)
S3_HEADING_RE = re.compile(
    rf"^({'|'.join(re.escape(h) for h in S3_HEADINGS)})[ \t]*\n[-=~]+\s*$",
    re.MULTILINE,
)

URI_HEADING_RE = re.compile(r"^URI[ \t]*\n[-=~^\"'`#*+]+\s*$", re.MULTILINE)

HEADER_ALIASES: dict[str, str] = {
    "parameter": "name",
    "name": "name",
    "header": "name",
    "mandatory": "mandatory",
    "mandatory (yes/no)": "mandatory",
    "required": "mandatory",
    "type": "type",
    "description": "description",
}

STRUCT_KEYWORDS_RE = re.compile(
    r"(?i)\blist\s+data\s+structure\b|\bdata\s+structure\b|"
    r"\bdictionary\b|\blist\b|"
    r"\barray\s+of\b|\bobjects?\b"
)
