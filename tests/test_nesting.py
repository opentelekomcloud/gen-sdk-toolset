"""S5 (#29): the pure anchor-based nested-struct resolver.

Exercises :func:`resolve_nested` on hand-built registries (no docutils):
multi-level nesting, each of the five failure codes, deep-copy independence,
and termination on cyclic input.
"""

from __future__ import annotations

from tools.scanner.parsers.docutils.nesting import (
    RefKind,
    RefTarget,
    resolve_nested,
)
from tools.scanner.parsers.docutils.table import TableExtraction
from tools.shared.ir import Parameter, ParameterType
from tools.shared.scan import IssueCode


def _extraction(rows: list[tuple[Parameter, str | None]]) -> TableExtraction:
    """Build a TableExtraction from (param, anchor) pairs; counters unused."""
    params = [p for p, _ in rows]
    anchors = [a for _, a in rows]
    return TableExtraction(
        parameters=params,
        ref_anchors=anchors,
        issues=[],
        fields_total=len(params),
        fields_recognized=len(params),
        fields_unknown_type=0,
        fields_failed=0,
    )


def _obj(name: str) -> Parameter:
    return Parameter(name=name, param_type=ParameterType.OBJECT)


def _str(name: str) -> Parameter:
    return Parameter(name=name, param_type=ParameterType.STRING)


def _table(*rows: tuple[Parameter, str | None]) -> RefTarget:
    return RefTarget(kind=RefKind.TABLE, table=_extraction(list(rows)))


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_multi_level_nesting() -> None:
    primary = {"body": _extraction([(_obj("firewall"), "a_option")])}
    registry = {
        "a_option": _table((_obj("tags"), "a_tag")),
        "a_tag": _table((_str("key"), None), (_str("value"), None)),
    }

    issues = resolve_nested(primary, registry)

    assert issues == []
    firewall = primary["body"].parameters[0]
    assert [c.name for c in firewall.children] == ["tags"]
    tags = firewall.children[0]
    assert [c.name for c in tags.children] == ["key", "value"]
    # Leaves stay leaves.
    assert tags.children[0].children == []


def test_primitive_rows_are_left_untouched() -> None:
    primary = {"body": _extraction([(_str("name"), None)])}
    assert resolve_nested(primary, {}) == []
    assert primary["body"].parameters[0].children == []


def test_same_struct_referenced_twice_gets_independent_children() -> None:
    primary = {
        "body": _extraction([(_obj("a"), "tag"), (_obj("b"), "tag")]),
    }
    registry = {"tag": _table((_str("key"), None))}

    resolve_nested(primary, registry)

    a, b = primary["body"].parameters
    assert a.children[0].name == b.children[0].name == "key"
    # Distinct objects — mutating one must not touch the other.
    assert a.children[0] is not b.children[0]
    a.children[0].name = "changed"
    assert b.children[0].name == "key"


# --------------------------------------------------------------------------- #
# Failure codes
# --------------------------------------------------------------------------- #
def test_dangling_anchor_not_found() -> None:
    # Same docid as the document, but no such table -> genuinely broken.
    primary = {"body": _extraction([(_obj("firewall"), "thisdoc__missing")])}
    issues = resolve_nested(primary, {}, doc_id="thisdoc")
    assert [i.code for i in issues] == [IssueCode.NESTED_TABLE_NOT_FOUND]
    assert issues[0].location == "firewall"
    assert issues[0].details == "thisdoc__missing"


def test_non_table_target() -> None:
    primary = {"body": _extraction([(_obj("firewall"), "para")])}
    registry = {"para": RefTarget(kind=RefKind.NON_TABLE)}
    issues = resolve_nested(primary, registry)
    assert [i.code for i in issues] == [IssueCode.NESTED_REF_NOT_A_TABLE]


def test_empty_table() -> None:
    primary = {"body": _extraction([(_obj("firewall"), "empty")])}
    registry = {"empty": RefTarget(kind=RefKind.TABLE, table=_extraction([]))}
    issues = resolve_nested(primary, registry)
    assert [i.code for i in issues] == [IssueCode.NESTED_TABLE_EMPTY]


def test_external_ref() -> None:
    # Anchor's docid ("otherdoc") differs from this document's -> external.
    primary = {"body": _extraction([(_obj("firewall"), "otherdoc__thing")])}
    issues = resolve_nested(primary, {}, doc_id="thisdoc")
    assert [i.code for i in issues] == [IssueCode.NESTED_REF_EXTERNAL]


def test_bare_cross_page_anchor_is_external() -> None:
    # A cross-page ref with no "__" (whole value is the docid) is external too.
    primary = {"body": _extraction([(_obj("firewall"), "vpc_api_0002")])}
    issues = resolve_nested(primary, {}, doc_id="thisdoc")
    assert [i.code for i in issues] == [IssueCode.NESTED_REF_EXTERNAL]


def test_foreign_docid_without_known_doc_id_is_not_found() -> None:
    # Without a known doc_id we can't classify external; default to not-found.
    primary = {"body": _extraction([(_obj("firewall"), "otherdoc__thing")])}
    issues = resolve_nested(primary, {})
    assert [i.code for i in issues] == [IssueCode.NESTED_TABLE_NOT_FOUND]


# --------------------------------------------------------------------------- #
# Cycles
# --------------------------------------------------------------------------- #
def test_self_reference_is_circular_and_terminates() -> None:
    # node -> node (self-referential tree)
    primary = {"body": _extraction([(_obj("node"), "node_t")])}
    registry = {"node_t": _table((_str("id"), None), (_obj("child"), "node_t"))}

    issues = resolve_nested(primary, registry)

    assert [i.code for i in issues] == [IssueCode.NESTED_CIRCULAR_REF]
    # First level resolved; recursion stopped at the repeated anchor.
    node = primary["body"].parameters[0]
    assert [c.name for c in node.children] == ["id", "child"]
    assert node.children[1].children == []


def test_mutual_cycle_terminates() -> None:
    primary = {"body": _extraction([(_obj("a"), "a_t")])}
    registry = {
        "a_t": _table((_obj("to_b"), "b_t")),
        "b_t": _table((_obj("to_a"), "a_t")),
    }

    issues = resolve_nested(primary, registry)

    assert [i.code for i in issues] == [IssueCode.NESTED_CIRCULAR_REF]


def test_repeated_sibling_ref_is_not_a_cycle() -> None:
    # The same struct referenced by two siblings is fine — `visiting` is
    # per-path, not global, so the second sibling still resolves.
    primary = {"body": _extraction([(_obj("a"), "leaf"), (_obj("b"), "leaf")])}
    registry = {"leaf": _table((_str("x"), None))}

    issues = resolve_nested(primary, registry)

    assert issues == []
    a, b = primary["body"].parameters
    assert a.children[0].name == "x"
    assert b.children[0].name == "x"
