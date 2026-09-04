"""Anchor-based resolution of nested object/array struct references.

A parameter whose type is an object or array-of-objects can carry a ``:ref:``
anchor. :mod:`.table` keeps that authored anchor in the same ``TableRow`` as
the parameter. This module follows those anchors and populates
:attr:`Parameter.children`.

The resolver takes the already-extracted primary tables and a
registry of ref targets, and attaches children to the parameters. Walking the doctree
to *build* the registry is the wire-in step's job; this module only
consumes it.

Registry shape
--------------
The registry classifies every known anchor as either a struct table
(:attr:`RefKind.TABLE`) or a non-table node (:attr:`RefKind.NON_TABLE`) — a
plain ``TableExtraction`` cannot express the latter. Repository context adds
cross-document tables to this registry before resolution. An unresolved OTC
anchor whose docid differs from the current document is reported as
``NESTED_REF_EXTERNAL``; other unresolved anchors are reported as
``NESTED_TABLE_NOT_FOUND``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tools.shared.ir import Parameter, ParameterType
from tools.shared.scan import Issue, IssueCode

from .references import RefKind, RefTarget
from .table import TableExtraction, TableRow


@dataclass
class _ResolutionState:
    registry: Mapping[str, RefTarget]
    label_tables: Mapping[str, TableExtraction]
    used_labels: set[str]
    used_tables: set[int]
    doc_id: str | None
    issues: list[Issue]


@dataclass(frozen=True)
class _TargetMatch:
    reference: str
    target: RefTarget


def resolve_nested(
    primary: dict[str, TableExtraction],
    registry: dict[str, RefTarget],
    doc_id: str | None = None,
    label_tables: dict[str, TableExtraction] | None = None,
    used_tables: set[int] | None = None,
) -> list[Issue]:
    """Attach children through explicit anchors or legacy parent-name labels."""
    labels = label_tables or {}

    state = _ResolutionState(
        registry=registry,
        label_tables=labels,
        used_labels=set(),
        used_tables=used_tables if used_tables is not None else set(),
        doc_id=doc_id,
        issues=[],
    )

    for extraction in primary.values():
        _resolve(
            extraction.rows,
            state,
            visiting=frozenset(),
        )
    state.issues.extend(_orphan_label_issues(labels, state.used_labels))
    return state.issues


def _resolve(
    rows: list[TableRow],
    state: _ResolutionState,
    visiting: frozenset[str],
) -> None:
    for row in rows:
        param = row.parameter
        match = _lookup_target(row, state=state)
        if match is None:
            continue
        table = _target_table(match, param, visiting=visiting, issues=state.issues)
        if table is None:
            continue

        _attach_and_recurse(
            param,
            table,
            match.reference,
            state,
            visiting,
        )


def _attach_and_recurse(
    param: Parameter,
    table: TableExtraction,
    match_reference: str,
    state: _ResolutionState,
    visiting: frozenset[str],
) -> None:
    state.used_tables.add(id(table))
    children = [child.model_copy(deep=True) for child in table.parameters]
    param.children = children
    if param.param_type is ParameterType.ARRAY:
        param.param_type = ParameterType.ARRAY_OF_OBJECTS
    _resolve(
        [
            TableRow(child, source.ref_anchor, source.description_anchors)
            for child, source in zip(children, table.rows)
        ],
        state,
        visiting | {match_reference},
    )


def _lookup_target(
    row: TableRow,
    state: _ResolutionState,
) -> _TargetMatch | None:
    """The structure this row refers to, by the first source that names one.

    An authored anchor - type cell, then name cell - settles the row on its own,
    including when it fails to resolve: it was written as a struct reference, so
    a broken one is a defect worth reporting rather than a reason to keep
    looking. Only a row that names nothing falls through to the legacy
    parent-name label, and then to its description.
    """
    if row.ref_anchor is not None:
        return _lookup_anchor(row.parameter, row.ref_anchor, state)
    label = _lookup_label(row.parameter, state)
    if label is not None:
        return label
    return _lookup_description(row.parameter, row.description_anchors, state)


def _lookup_description(
    param: Parameter,
    anchors: tuple[str, ...],
    state: _ResolutionState,
) -> _TargetMatch | None:
    """The one structure table a description points at, or ``None``.

    A description is prose, so a ref inside it is a candidate and not an
    assertion - api-ref cells link to status codes, error codes and neighbouring
    pages as a matter of course. Only anchors the registry already knows to be
    struct tables are considered, and only when exactly one of them survives:
    two leave nothing to say which structure belongs to this row, and guessing
    between them would attach somebody else's fields.

    Nothing is reported when no candidate survives. The row keeps the children
    it had, and a struct table that went unclaimed is still accounted for -
    `report_unused_tables` raises `NESTED_PARENT_NOT_FOUND` for it.

    Carrying a table is what makes a target a candidate: a `RefKind.NON_TABLE`
    entry has none by construction, so a link to a status-code page drops out
    here without a second test for its kind.
    """
    if not param.param_type.supports_children:
        return None

    candidates = [
        (anchor, target)
        for anchor, target in ((a, state.registry.get(a)) for a in anchors)
        if target is not None and target.table is not None
    ]
    if len(candidates) != 1:
        return None

    anchor, target = candidates[0]
    return _TargetMatch(reference=anchor, target=target)


def _lookup_label(
    param: Parameter,
    state: _ResolutionState,
) -> _TargetMatch | None:
    if not param.param_type.supports_children:
        return None
    table = state.label_tables.get(param.name)
    if table is None:
        return None
    state.used_labels.add(param.name)
    return _TargetMatch(
        reference=f"label:{param.name}",
        target=RefTarget(kind=RefKind.TABLE, table=table),
    )


def _lookup_anchor(
    param: Parameter,
    anchor: str,
    state: _ResolutionState,
) -> _TargetMatch | None:
    target = state.registry.get(anchor)
    if target is not None:
        return _TargetMatch(reference=anchor, target=target)

    code = (
        IssueCode.NESTED_REF_EXTERNAL
        if _is_external(anchor, state.doc_id)
        else IssueCode.NESTED_TABLE_NOT_FOUND
    )
    _flag(state.issues, code, param, anchor)
    return None


def _target_table(
    match: _TargetMatch,
    param: Parameter,
    *,
    visiting: frozenset[str],
    issues: list[Issue],
) -> TableExtraction | None:
    if match.target.kind is RefKind.NON_TABLE or match.target.table is None:
        _flag(issues, IssueCode.NESTED_REF_NOT_A_TABLE, param, match.reference)
        return None
    if not match.target.table.parameters:
        _flag(issues, IssueCode.NESTED_TABLE_EMPTY, param, match.reference)
        return None
    if match.reference in visiting:
        _flag(issues, IssueCode.NESTED_CIRCULAR_REF, param, match.reference)
        return None
    return match.target.table


def _orphan_label_issues(
    label_tables: dict[str, TableExtraction],
    used_labels: set[str],
) -> list[Issue]:
    return [
        Issue(
            code=IssueCode.NESTED_PARENT_NOT_FOUND,
            location=parent_name,
            details="nested table has no matching object or array parameter",
        )
        for parent_name in label_tables
        if parent_name not in used_labels
    ]


def _is_external(anchor: str, doc_id: str | None) -> bool:
    """True when ``anchor`` targets a different document than ``doc_id``.

    OTC anchors are ``<docid>__<local>`` (a bare cross-page ref has no ``__``,
    so its whole value is the docid). A docid other than this document's means
    the ref leaves the document. Without a known ``doc_id`` we can't tell, so
    we do not classify it as external.
    """
    if doc_id is None:
        return False
    return anchor.split("__", 1)[0] != doc_id


def _flag(issues: list[Issue], code: IssueCode, param: Parameter, anchor: str) -> None:
    issues.append(Issue(code=code, location=param.name, details=anchor))
