"""Anchor-based resolution of nested object/array struct references.

A parameter whose type is an object or array-of-objects carries a ``:ref:``
anchor (captured by :mod:`.table` as ``TableExtraction.ref_anchors``) that
points at the struct's definition table elsewhere in the same document. This
module follows those anchors and populates :attr:`Parameter.children`.

The resolver is **pure**: it takes the already-extracted primary tables and a
registry of ref targets, and returns the issues it found. Walking the doctree
to *build* the registry is the wire-in step's job; this module only
consumes it.

Registry shape
--------------
The registry classifies each *in-document* anchor as either a struct table
(:attr:`RefKind.TABLE`) or a non-table node (:attr:`RefKind.NON_TABLE`) — a
plain ``TableExtraction`` cannot express the latter. Two more outcomes are
decided *without* the registry, at the ``target is None`` branch: OTC anchors
are ``<docid>__<local>`` where ``docid`` is the document's own label, so an
anchor whose docid differs from this document's points into another document
(``NESTED_REF_EXTERNAL``); otherwise it is a genuine dangling ref
(``NESTED_TABLE_NOT_FOUND``). ``primary`` stays a ``dict[str, TableExtraction]``
(one per parameter-bearing section) since those are always real tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tools.shared.ir import Parameter, ParameterType
from tools.shared.scan import Issue, IssueCode

from .table import TableExtraction


class RefKind(str, Enum):
    """What an in-document ref anchor resolves to, classified by the wire-in.

    Cross-document refs are not registry entries — they are detected from the
    anchor's docid at lookup time (see :func:`_is_external`).
    """

    TABLE = "table"  # a struct definition table in this document
    NON_TABLE = "non_table"  # anchor exists but points at a non-table node


@dataclass(frozen=True)
class RefTarget:
    """A resolved ref anchor. ``table`` is set only when ``kind is TABLE``."""

    kind: RefKind
    table: TableExtraction | None = None


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
    used_labels: set[str] = set()
    resolved_tables = used_tables if used_tables is not None else set()
    issues: list[Issue] = []
    for extraction in primary.values():
        _resolve(
            extraction.parameters,
            extraction.ref_anchors,
            registry,
            labels,
            used_labels,
            resolved_tables,
            doc_id=doc_id,
            visiting=frozenset(),
            issues=issues,
        )
    issues.extend(_orphan_label_issues(labels, used_labels))
    return issues


def _resolve(
    params: list[Parameter],
    anchors: list[str | None],
    registry: dict[str, RefTarget],
    label_tables: dict[str, TableExtraction],
    used_labels: set[str],
    used_tables: set[int],
    doc_id: str | None,
    visiting: frozenset[str],
    issues: list[Issue],
) -> None:
    for param, anchor in zip(params, anchors):
        match = _lookup_target(
            param,
            anchor,
            registry=registry,
            label_tables=label_tables,
            used_labels=used_labels,
            doc_id=doc_id,
            issues=issues,
        )
        if match is None:
            continue
        table = _target_table(match, param, visiting=visiting, issues=issues)
        if table is None:
            continue

        used_tables.add(id(table))
        children = [child.model_copy(deep=True) for child in table.parameters]
        param.children = children
        if param.param_type is ParameterType.ARRAY:
            param.param_type = ParameterType.ARRAY_OF_OBJECTS
        _resolve(
            children,
            table.ref_anchors,
            registry,
            label_tables,
            used_labels,
            used_tables,
            doc_id,
            visiting | {match.reference},
            issues,
        )


def _lookup_target(
    param: Parameter,
    anchor: str | None,
    *,
    registry: dict[str, RefTarget],
    label_tables: dict[str, TableExtraction],
    used_labels: set[str],
    doc_id: str | None,
    issues: list[Issue],
) -> _TargetMatch | None:
    if anchor is None:
        if not param.param_type.supports_children:
            return None
        table = label_tables.get(param.name)
        if table is None:
            return None
        used_labels.add(param.name)
        return _TargetMatch(
            reference=f"label:{param.name}",
            target=RefTarget(kind=RefKind.TABLE, table=table),
        )

    target = registry.get(anchor)
    if target is not None:
        return _TargetMatch(reference=anchor, target=target)

    code = (
        IssueCode.NESTED_REF_EXTERNAL
        if _is_external(anchor, doc_id)
        else IssueCode.NESTED_TABLE_NOT_FOUND
    )
    _flag(issues, code, param, anchor)
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
