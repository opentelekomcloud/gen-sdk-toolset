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

from tools.domain.report import Issue, IssueCode
from tools.shared.ir import Parameter

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


def resolve_nested(
    primary: dict[str, TableExtraction],
    registry: dict[str, RefTarget],
    doc_id: str | None = None,
) -> list[Issue]:
    """Populate ``children`` for every object/array param in ``primary``.

    Mutates the parameters in ``primary`` in place (attaching resolved
    ``children``) and returns the list of issues for anchors that could not
    be resolved. ``registry`` maps a ref anchor to its :class:`RefTarget`.
    ``doc_id`` is this document's own label; it lets an unresolved anchor
    with a foreign docid be reported as external rather than dangling. With
    no ``doc_id`` the external check is skipped (every miss is "not found").
    """
    issues: list[Issue] = []
    for extraction in primary.values():
        _resolve(
            extraction.parameters,
            extraction.ref_anchors,
            registry,
            doc_id=doc_id,
            visiting=frozenset(),
            issues=issues,
        )
    return issues


def _resolve(
    params: list[Parameter],
    anchors: list[str | None],
    registry: dict[str, RefTarget],
    doc_id: str | None,
    visiting: frozenset[str],
    issues: list[Issue],
) -> None:
    for param, anchor in zip(params, anchors):
        if anchor is None:
            continue  # primitive / no ref → leaf

        target = registry.get(anchor)
        if target is None:
            # Not a target in this document: either it points into another
            # doc (foreign docid) or it is a genuine dangling ref.
            code = (
                IssueCode.NESTED_REF_EXTERNAL
                if _is_external(anchor, doc_id)
                else IssueCode.NESTED_TABLE_NOT_FOUND
            )
            _flag(issues, code, param, anchor)
            continue
        if target.kind is RefKind.NON_TABLE or target.table is None:
            _flag(issues, IssueCode.NESTED_REF_NOT_A_TABLE, param, anchor)
            continue
        if not target.table.parameters:
            _flag(issues, IssueCode.NESTED_TABLE_EMPTY, param, anchor)
            continue
        if anchor in visiting:  # cycle on the current path (A → … → A)
            _flag(issues, IssueCode.NESTED_CIRCULAR_REF, param, anchor)
            continue

        # Deep-copy so two params referencing the same struct get independent
        # subtrees and nothing in the registry is mutated.
        children = [child.model_copy(deep=True) for child in target.table.parameters]
        param.children = children
        _resolve(
            children,
            target.table.ref_anchors,
            registry,
            doc_id,
            visiting | {anchor},
            issues,
        )


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
