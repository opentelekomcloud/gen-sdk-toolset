"""Parameter table extraction from docutils table nodes.

OTC docs use a mix of grid tables (``+----+`` borders) and simple tables
(``=== ===`` borders). docutils normalises both into the same node tree,
so this parser doesn't need to care which surface form was used.

Columns are identified by *header text* (not by index) because some doc
styles reorder them — for example OBS request-parameter tables put
``Mandatory`` after ``Description``. Type column is optional (URI tables
in older docs omit it). ``Mandatory`` is also optional (response-side
tables don't have one).

The parser returns:

* a list of :class:`tools.domain.ir.Parameter` (one per body row), and
* counters that feed :class:`SectionResult` field-level metrics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from docutils import nodes

from tools.domain.report import Issue, IssueCode
from tools.shared.ir import Parameter, ParameterType

# Max length of free-text `details` we attach to diagnostic issues.
DETAILS_MAX = 80

# Column-header aliases mapped to canonical column keys. Comparison is
# case-insensitive on whitespace-stripped text.
_HEADER_ALIASES: dict[str, str] = {
    "parameter": "name",
    "name": "name",
    "header": "name",  # OBS header tables
    "mandatory": "mandatory",
    "mandatory (yes/no)": "mandatory",
    "required": "mandatory",
    "type": "type",
    "description": "description",
}


# Type-text → ParameterType. Loose matching on lower-cased text. Sphinx
# :ref: markup is already resolved to its visible label at parse time by the
# passthrough role registered in doc_parser (_ensure_roles), so no stripping
# is needed here — see tests/test_ref_resolution.py.
def _classify_type(raw: str) -> ParameterType:
    if not raw:
        return ParameterType.UNKNOWN
    lower = raw.strip().lower()

    # Composite array types first (more specific).
    if re.search(r"\barray\s+of\s+strings?\b", lower):
        return ParameterType.ARRAY_OF_STRINGS
    if re.search(r"\barray\s+of\s+integers?\b", lower):
        return ParameterType.ARRAY_OF_INTEGERS
    if re.search(r"\barray\s+of\s+", lower) and "object" in lower:
        return ParameterType.ARRAY_OF_OBJECTS
    if lower.startswith("array of "):
        return ParameterType.ARRAY_OF_OBJECTS  # named struct → object array

    # Bare composites
    if lower == "array" or lower.startswith("array "):
        return ParameterType.ARRAY

    # Primitives — match the longest prefix word.
    for word, kind in (
        ("string", ParameterType.STRING),
        ("integer", ParameterType.INTEGER),
        ("long", ParameterType.LONG),
        ("float", ParameterType.FLOAT),
        ("double", ParameterType.DOUBLE),
        ("boolean", ParameterType.BOOLEAN),
        ("bool", ParameterType.BOOLEAN),
        ("object", ParameterType.OBJECT),
    ):
        if re.search(rf"\b{word}\b", lower):
            return ParameterType.OBJECT if "object" in lower else kind

    return ParameterType.UNKNOWN


# Struct/array keywords stripped from a type cell to leave the bare struct
# name (e.g. "Array of RequestTag objects" -> "RequestTag"). A cell that is
# only keywords ("object", "Array of objects") leaves nothing -> no type_name.
# `\s+` tolerates irregular whitespace in "array of" (double spaces, newlines).
_STRUCT_KEYWORDS_RE = re.compile(r"(?i)\barray\s+of\b|\bobjects?\b")

# Parameter types that carry a referenced struct name worth preserving.
_STRUCT_TYPES = frozenset({ParameterType.OBJECT, ParameterType.ARRAY_OF_OBJECTS})


@dataclass
class TableExtraction:
    """Result of parsing one parameter table."""

    parameters: list[Parameter]
    # Struct ref anchor (`:ref:` target) for each parameter, aligned 1:1 with
    # ``parameters``. ``None`` for primitives / rows without a struct ref.
    ref_anchors: list[str | None]
    issues: list[Issue]
    fields_total: int
    fields_recognized: int
    fields_unknown_type: int
    fields_failed: int


def extract_parameter_table(table: nodes.table) -> TableExtraction:
    """Walk one docutils table and return Parameters + metrics.

    Tolerates missing Mandatory or Type columns. Logs structural issues
    (no header row, unrecognised header layout) without raising.
    """
    issues: list[Issue] = []
    parameters: list[Parameter] = []
    ref_anchors: list[str | None] = []

    column_map = _build_column_map(table)
    if column_map is None or "name" not in column_map:
        issues.append(
            Issue(
                code=IssueCode.UNEXPECTED_COLUMNS,
                details=(
                    f"Could not identify columns in table: {_header_preview(table)}"
                ),
            )
        )
        return TableExtraction(
            parameters=[],
            ref_anchors=[],
            issues=issues,
            fields_total=0,
            fields_recognized=0,
            fields_unknown_type=0,
            fields_failed=0,
        )

    body_rows = _body_rows(table)

    fields_total = 0
    fields_recognized = 0
    fields_unknown_type = 0
    fields_failed = 0

    for row_idx, row in enumerate(body_rows, start=1):
        fields_total += 1
        try:
            entries = list(row.children)
            cells = [_cell_text(entry) for entry in entries]
            name = cells[column_map["name"]].strip()
            type_raw = cells[column_map["type"]].strip() if "type" in column_map else ""
            mandatory = (
                _parse_mandatory(cells[column_map["mandatory"]])
                if "mandatory" in column_map
                else False
            )
            description = (
                cells[column_map["description"]].strip()
                if "description" in column_map
                else ""
            )

            if not name:
                # Row has no parameter name — count as failed.
                fields_failed += 1
                issues.append(
                    Issue(
                        code=IssueCode.MALFORMED_GRID_TABLE,
                        location=f"row {row_idx}",
                        details="empty parameter name",
                    )
                )
                continue

            param_type = _classify_type(type_raw)
            is_struct = param_type in _STRUCT_TYPES
            type_name = _struct_type_name(type_raw) if is_struct else None
            # The struct ref anchor lives on the type cell in some corpora
            # (VPC: ":ref:`CreateFirewallOption <...>` object") and on the
            # name cell in others (IAM: ":ref:`protect_policy <...>`" with a
            # bare "object" type). Capture it for struct-typed params only,
            # preferring the type cell, so primitive rows never pick up an
            # unrelated name-cell ref.
            anchor = _struct_anchor(entries, column_map) if is_struct else None

            parameters.append(
                Parameter(
                    name=name,
                    param_type=param_type,
                    mandatory=mandatory,
                    description=description,
                    type_name=type_name,
                )
            )
            ref_anchors.append(anchor)

            if not type_raw:
                # Recognised (we have a name) but no type cell at all.
                # That's OK for URI tables; counts as "recognized" still.
                fields_recognized += 1
            elif param_type is ParameterType.UNKNOWN:
                fields_unknown_type += 1
                issues.append(
                    Issue(
                        code=IssueCode.UNKNOWN_TYPE_FORMAT,
                        location=f"row {row_idx}",
                        details=type_raw[:DETAILS_MAX],
                    )
                )
            else:
                fields_recognized += 1
        except (IndexError, ValueError) as e:  # pragma: no cover - defensive
            fields_failed += 1
            issues.append(
                Issue(
                    code=IssueCode.MALFORMED_GRID_TABLE,
                    location=f"row {row_idx}",
                    details=str(e),
                )
            )

    # ref_anchors is appended in lockstep with parameters, so the resolver
    # (S5) can zip them safely. Guard the invariant rather than trust it.
    assert len(ref_anchors) == len(parameters), (
        f"ref_anchors ({len(ref_anchors)}) misaligned with "
        f"parameters ({len(parameters)})"
    )

    return TableExtraction(
        parameters=parameters,
        ref_anchors=ref_anchors,
        issues=issues,
        fields_total=fields_total,
        fields_recognized=fields_recognized,
        fields_unknown_type=fields_unknown_type,
        fields_failed=fields_failed,
    )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _build_column_map(table: nodes.table) -> dict[str, int] | None:
    """Build {canonical_name → column_index} from the table's header row."""
    thead = next(iter(table.findall(nodes.thead)), None)
    if thead is None:
        return None
    header_row = next(iter(thead.findall(nodes.row)), None)
    if header_row is None:
        return None

    column_map: dict[str, int] = {}
    for idx, entry in enumerate(header_row.children):
        text = _cell_text(entry).strip().lower()
        canonical = _HEADER_ALIASES.get(text)
        if canonical is not None and canonical not in column_map:
            column_map[canonical] = idx
    return column_map


def _body_rows(table: nodes.table) -> list[nodes.row]:
    """All rows in the table's body section(s)."""
    rows: list[nodes.row] = []
    for tbody in table.findall(nodes.tbody):
        rows.extend(tbody.findall(nodes.row))
    return rows


def _cell_text(entry: nodes.Element) -> str:
    """Extract the textual content of a single table cell."""
    return entry.astext()


def _ref_anchor(entry: nodes.Element) -> str | None:
    """First ``ref_target`` on an inline node in a cell, else ``None``.

    The passthrough role (see doc_parser) attaches ``ref_target`` to the
    inline node it emits for a ``:ref:``. One struct ref per cell in practice.
    """
    for inline in entry.findall(nodes.inline):
        anchor = inline.get("ref_target")
        if anchor:
            return anchor
    return None


def _struct_anchor(
    entries: list[nodes.Element], column_map: dict[str, int]
) -> str | None:
    """Struct ref anchor for a row: type cell first, then name cell.

    Type-cell refs (VPC) win over name-cell refs (IAM) when both exist, so a
    ``:ref:`` on the type always takes precedence.
    """
    for column in ("type", "name"):
        idx = column_map.get(column)
        if idx is None:
            continue
        anchor = _ref_anchor(entries[idx])
        if anchor:
            return anchor
    return None


def _struct_type_name(raw_type: str) -> str | None:
    """Bare struct name from an object/array type cell, or ``None``.

    ``"CreateFirewallOption object"`` -> ``"CreateFirewallOption"``;
    ``"Array of RequestTag objects"`` -> ``"RequestTag"``; a cell that is
    only structural keywords (``"object"``, ``"Array of objects"``) -> ``None``.
    """
    name = _STRUCT_KEYWORDS_RE.sub(" ", raw_type)
    name = re.sub(r"\s+", " ", name).strip()
    return name or None


def _parse_mandatory(text: str) -> bool:
    cleaned = text.strip().lower()
    return cleaned in {"yes", "true", "required"}


def _header_preview(table: nodes.table) -> str:
    """One-line preview of the header row for diagnostic messages."""
    thead = next(iter(table.findall(nodes.thead)), None)
    if thead is None:
        return "(no header row)"
    row = next(iter(thead.findall(nodes.row)), None)
    if row is None:
        return "(empty header)"
    return " | ".join(_cell_text(e).strip() for e in row.children)
