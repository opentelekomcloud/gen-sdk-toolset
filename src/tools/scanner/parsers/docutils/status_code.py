"""Status-code table parsing.

Shaped after :mod:`.table`, because the problem is the same one: a docutils
table whose columns are identified by their header text, tolerant of the
variations api-ref actually contains. What differs is the output - a
:class:`StatusCode` carries a code and a description and nothing else.

Three layouts appear in the corpus and all three are read here:

* a two-column grid table (``Status Code`` / ``Description``);
* a three-column simple table (``Status Code`` / ``Status`` / ``Description``),
  where the middle column is the HTTP reason phrase;
* a bare simple table with no ``.. table::`` title, listing only the codes this
  API documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from docutils import nodes

from tools.shared.ir import StatusCode
from tools.shared.scan import Issue, IssueCode

from .rst_nodes import body_rows, build_column_map, cell_text, header_preview

#: Header text to the column it names. Only the two columns a `StatusCode` has
#: are mapped: a reason-phrase column (``Status`` holding "OK") is left alone
#: for the same reason `table.py` leaves columns it does not model alone - the
#: IR has nowhere to put it, and "OK" restates the code rather than the
#: document.
_HEADER_ALIASES: dict[str, str] = {
    "status code": "code",
    "code": "code",
    "description": "description",
    "status description": "description",
}


@dataclass
class StatusCodeExtraction:
    """Result of parsing one status-code table."""

    codes: list[StatusCode] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def extend(self, other: StatusCodeExtraction) -> None:
        self.codes.extend(other.codes)
        self.issues.extend(other.issues)


def extract_status_code_table(table: nodes.table) -> StatusCodeExtraction:
    """Walk one docutils table and return the status codes it lists.

    A table whose code column cannot be identified yields no rows and one
    ``UNEXPECTED_COLUMNS`` issue naming the header it could not read - the same
    bargain `extract_parameter_table` makes, so an unreadable table is counted
    rather than silently producing an empty section.
    """
    extraction = StatusCodeExtraction()

    column_map = build_column_map(table, _HEADER_ALIASES)
    if column_map is None or "code" not in column_map:
        extraction.issues.append(
            Issue(
                code=IssueCode.UNEXPECTED_COLUMNS,
                details=(
                    "Could not identify status code columns in table: "
                    f"{header_preview(table)}"
                ),
            )
        )
        return extraction

    for row_index, row in enumerate(body_rows(table), start=1):
        _append_status_code_row(extraction, row, row_index, column_map)

    return extraction


def _append_status_code_row(
    extraction: StatusCodeExtraction,
    row: nodes.row,
    row_index: int,
    column_map: dict[str, int],
) -> None:
    cells = [cell_text(entry) for entry in row.children]
    try:
        code = cells[column_map["code"]].strip()
    except IndexError:
        code = ""
    if not code:
        # A row that names no code is not a status code. Saying so keeps it
        # from vanishing between the table and the section.
        extraction.issues.append(
            Issue(
                code=IssueCode.MALFORMED_GRID_TABLE,
                location=f"row {row_index}",
                details="status code row has no code",
            )
        )
        return

    index = column_map.get("description")
    description = (
        cells[index].strip() if index is not None and index < len(cells) else ""
    )
    extraction.codes.append(StatusCode(code=code, description=description))
