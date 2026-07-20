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

from tools.shared.ir import SectionName

from .patterns import (
    NESTED_LABEL_PATTERNS,
    PARAM_KEYWORDS,
    SECTION_VARIANTS,
    TABLE_TITLE_PATTERNS,
)
from .types import SectionKind, TableTarget

_DEFAULT_TABLE_SECTIONS = {
    SectionKind.URI: SectionName.PATH_PARAMS,
    SectionKind.REQUEST: SectionName.BODY,
    SectionKind.RESPONSE: SectionName.RESPONSE,
}


def classify_section_title(title: str) -> SectionKind:
    """Classify a section heading text into a :class:`SectionKind`."""
    key = title.strip().lower()
    for kind, variants in SECTION_VARIANTS.items():
        if key in variants:
            return kind
    return SectionKind.OTHER


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
    for pattern, key in TABLE_TITLE_PATTERNS:
        if pattern.search(title):
            return key

    # Fall back on enclosing section if the title looks like a primary parameter table.
    if in_section in _DEFAULT_TABLE_SECTIONS:
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
    for pattern in NESTED_LABEL_PATTERNS:
        match = pattern.match(cleaned)
        if match:
            return match.group(1).strip()
    return None


def _looks_like_parameter_table(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in PARAM_KEYWORDS)
