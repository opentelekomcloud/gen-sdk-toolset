"""Common operations for docutils AST nodes."""

from __future__ import annotations

from docutils import nodes


def all_ref_targets(node: nodes.Element) -> tuple[str, ...]:
    """Every inline ref_target anchor within a node, in order, without repeats.

    A cell may carry more than one - a description linking to both a structure
    table and a status-code page - and which of them means anything is a
    question for the caller, not for this traversal.
    """
    seen: dict[str, None] = {}
    for inline in node.findall(nodes.inline):
        target = inline.get("ref_target")
        if target:
            seen.setdefault(str(target), None)
    return tuple(seen)


def first_ref_target(node: nodes.Element) -> str | None:
    """Find the first inline ref_target anchor within a node."""
    return next(iter(all_ref_targets(node)), None)


def first_authored_name(node: nodes.Element) -> str | None:
    """Get the first explicitly authored name (label/anchor) of a node."""
    names = node.get("names", ())
    return str(names[0]) if names else None


def cell_text(entry: nodes.Element) -> str:
    """Extract the textual content of a single table cell."""
    return entry.astext()


def body_rows(table: nodes.table) -> list[nodes.row]:
    """All rows in the table's body section(s)."""
    rows: list[nodes.row] = []
    for tbody in table.findall(nodes.tbody):
        rows.extend(tbody.findall(nodes.row))
    return rows


def build_column_map(
    table: nodes.table, aliases: dict[str, str]
) -> dict[str, int] | None:
    """Build {canonical_name → column_index} from the table's header row.

    `aliases` decides what the caller considers a column worth keeping; a
    header it does not name is skipped, so a table may carry columns the caller
    has nowhere to put. `None` means the table has no header row at all, which
    is a different thing from a header nothing matched.
    """
    thead = next(iter(table.findall(nodes.thead)), None)
    if thead is None:
        return None
    header_row = next(iter(thead.findall(nodes.row)), None)
    if header_row is None:
        return None

    column_map: dict[str, int] = {}
    for index, entry in enumerate(header_row.children):
        canonical = aliases.get(cell_text(entry).strip().lower())
        if canonical is not None and canonical not in column_map:
            column_map[canonical] = index
    return column_map


def header_preview(table: nodes.table) -> str:
    """One-line preview of the header row for diagnostic messages."""
    thead = next(iter(table.findall(nodes.thead)), None)
    if thead is None:
        return "(no header row)"
    row = next(iter(thead.findall(nodes.row)), None)
    if row is None:
        return "(empty header)"
    return " | ".join(cell_text(entry).strip() for entry in row.children)
