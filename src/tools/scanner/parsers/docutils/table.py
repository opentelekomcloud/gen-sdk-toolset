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

* a list of :class:`tools.shared.ir.Parameter` (one per body row), and
* counters that feed :class:`SectionScanResult` field-level metrics.
"""

from __future__ import annotations

from dataclasses import dataclass

from docutils import nodes

from tools.shared.ir import Parameter, ParameterType
from tools.shared.scan import Issue, IssueCode

from .diagnostics import ISSUE_DETAILS_MAX
from .field_type import parse_field_type, parse_mandatory
from .patterns import HEADER_ALIASES
from .rst_nodes import (
    all_ref_targets,
    body_rows,
    build_column_map,
    cell_text,
    first_ref_target,
    header_preview,
)


@dataclass
class TableRow:
    """A parsed parameter kept together with the refs its row was written with.

    ``ref_anchor`` is authored *as* a struct reference - it sits in the type or
    name cell, where nothing else belongs. ``description_anchors`` are only
    candidates: a description is prose, and its links point at status codes and
    other pages as often as at a structure.
    """

    parameter: Parameter
    ref_anchor: str | None = None
    description_anchors: tuple[str, ...] = ()


@dataclass
class ExtractionMetrics:
    fields_total: int = 0
    fields_recognized: int = 0
    fields_unknown_type: int = 0
    fields_failed: int = 0

    def merge(self, other: ExtractionMetrics) -> None:
        self.fields_total += other.fields_total
        self.fields_recognized += other.fields_recognized
        self.fields_unknown_type += other.fields_unknown_type
        self.fields_failed += other.fields_failed


@dataclass
class TableExtraction:
    """Result of parsing one parameter table."""

    rows: list[TableRow]
    issues: list[Issue]
    metrics: ExtractionMetrics

    @property
    def parameters(self) -> list[Parameter]:
        return [row.parameter for row in self.rows]

    def extend(self, other: TableExtraction) -> None:
        self.rows.extend(other.rows)
        self.issues.extend(other.issues)
        self.metrics.merge(other.metrics)


def extract_parameter_table(table: nodes.table) -> TableExtraction:
    """Walk one docutils table and return Parameters + metrics.

    Tolerates missing Mandatory or Type columns. Logs structural issues
    (no header row, unrecognised header layout) without raising.
    """
    extraction = TableExtraction(
        rows=[],
        issues=[],
        metrics=ExtractionMetrics(),
    )

    column_map = build_column_map(table, HEADER_ALIASES)
    if column_map is None or "name" not in column_map:
        extraction.issues.append(
            Issue(
                code=IssueCode.UNEXPECTED_COLUMNS,
                details=(
                    f"Could not identify columns in table: {header_preview(table)}"
                ),
            )
        )
        return extraction

    for row_idx, row in enumerate(body_rows(table), start=1):
        extraction.metrics.fields_total += 1
        _append_parameter_row(extraction, row, row_idx, column_map)

    return extraction


def _append_parameter_row(
    extraction: TableExtraction,
    row: nodes.row,
    row_idx: int,
    column_map: dict[str, int],
) -> None:
    try:
        param_row, type_raw = _extract_parameter_row(row, column_map)
    except (IndexError, ValueError) as exc:  # pragma: no cover - defensive
        extraction.metrics.fields_failed += 1
        extraction.issues.append(
            Issue(
                code=IssueCode.MALFORMED_GRID_TABLE,
                location=f"row {row_idx}",
                details=str(exc),
            )
        )
        return

    extraction.rows.append(param_row)
    if type_raw and param_row.parameter.param_type is ParameterType.UNKNOWN:
        extraction.metrics.fields_unknown_type += 1
        extraction.issues.append(
            Issue(
                code=IssueCode.UNKNOWN_TYPE_FORMAT,
                location=f"row {row_idx}",
                details=type_raw[:ISSUE_DETAILS_MAX],
            )
        )
    else:
        extraction.metrics.fields_recognized += 1


def _extract_parameter_row(
    row: nodes.row,
    column_map: dict[str, int],
) -> tuple[TableRow, str]:
    entries = list(row.children)
    cells = [cell_text(entry) for entry in entries]
    name = cells[column_map["name"]].strip()
    if not name:
        raise ValueError("empty parameter name")

    type_raw = cells[column_map["type"]].strip() if "type" in column_map else ""
    mandatory = (
        parse_mandatory(cells[column_map["mandatory"]])
        if "mandatory" in column_map
        else False
    )
    description = (
        cells[column_map["description"]].strip() if "description" in column_map else ""
    )
    field = parse_field_type(type_raw)
    parameter = Parameter(
        name=name,
        param_type=field.param_type,
        element_type=field.element_type,
        mandatory=mandatory,
        description=description,
        type_name=field.type_name,
    )
    return (
        TableRow(
            parameter=parameter,
            # Only a cell that could hold a structure is searched for a
            # reference to one: an array of strings names nothing to resolve.
            ref_anchor=(
                _struct_anchor(entries, column_map)
                if parameter.supports_children
                else None
            ),
            # Same gate: a cell that cannot hold a structure has no candidates
            # worth collecting, so an array of strings walks no descriptions.
            description_anchors=(
                _description_anchors(entries, column_map)
                if parameter.supports_children
                else ()
            ),
        ),
        type_raw,
    )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _struct_anchor(
    entries: list[nodes.Element], column_map: dict[str, int]
) -> str | None:
    """Struct ref anchor for a row: type cell first, then name cell."""
    for column in ("type", "name"):
        idx = column_map.get(column)
        if idx is None:
            continue
        anchor = first_ref_target(entries[idx])
        if anchor:
            return anchor
    return None


def _description_anchors(
    entries: list[nodes.Element], column_map: dict[str, int]
) -> tuple[str, ...]:
    """Every ref anchor in a row's description cell, in the order written.

    Kept whole rather than reduced to the first: which of a description's links
    names this row's structure - if any does - is a question only the reference
    registry can answer, and it is not built yet.
    """
    idx = column_map.get("description")
    if idx is None:
        return ()
    return all_ref_targets(entries[idx])
