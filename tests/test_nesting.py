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
from tools.scanner.parsers.docutils.table import (
    ExtractionMetrics,
    TableExtraction,
    TableRow,
)
from tools.shared.ir import Parameter, ParameterType
from tools.shared.scan import IssueCode

#: A row as these tests write one: a parameter, its authored anchor, and
#: optionally the ref candidates found in its description.
_Row = tuple[Parameter, str | None] | tuple[Parameter, str | None, tuple[str, ...]]


def _extraction(rows: list[_Row]) -> TableExtraction:
    """TableExtraction from `(param, anchor[, description])`; counters unused."""
    return TableExtraction(
        rows=[TableRow(*row) for row in rows],
        issues=[],
        metrics=ExtractionMetrics(
            fields_total=len(rows),
            fields_recognized=len(rows),
            fields_unknown_type=0,
            fields_failed=0,
        ),
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


# --------------------------------------------------------------------------- #
# References found in the description cell
# --------------------------------------------------------------------------- #
def _described(parameter: Parameter, *description_anchors: str) -> _Row:
    """A row whose only refs sit in its description."""
    return (parameter, None, description_anchors)


def test_an_object_resolves_from_its_description() -> None:
    primary = {"body": _extraction([_described(_obj("firewall"), "opt")])}
    registry = {"opt": _table((_str("name"), None))}

    issues = resolve_nested(primary, registry)

    assert issues == []
    assert [c.name for c in primary["body"].parameters[0].children] == ["name"]


def test_an_object_array_resolves_from_its_description() -> None:
    """The `tags | Array of objects | ... see Table 2` shape, which is where
    this form actually appears."""
    tags = Parameter(name="tags", param_type=ParameterType.ARRAY_OF_OBJECTS)
    primary = {"body": _extraction([_described(tags, "tag_table")])}
    registry = {"tag_table": _table((_str("key"), None), (_str("value"), None))}

    issues = resolve_nested(primary, registry)

    assert issues == []
    assert [c.name for c in tags.children] == ["key", "value"]


def test_a_bare_array_resolves_and_is_promoted() -> None:
    """An `Array` cell that turns out to hold a struct becomes an object array,
    the same as it does through an authored anchor."""
    items = Parameter(name="items", param_type=ParameterType.ARRAY)
    primary = {"body": _extraction([_described(items, "leaf")])}

    assert resolve_nested(primary, {"leaf": _table((_str("x"), None))}) == []
    assert items.param_type is ParameterType.ARRAY_OF_OBJECTS
    assert [c.name for c in items.children] == ["x"]


def test_the_type_cell_wins_over_the_description() -> None:
    """Priority, and the reason for it: the type cell was authored *as* a struct
    reference, so it decides even when the description offers another."""
    primary = {"body": _extraction([(_obj("a"), "from_type", ("from_description",))])}
    registry = {
        "from_type": _table((_str("chosen"), None)),
        "from_description": _table((_str("ignored"), None)),
    }

    issues = resolve_nested(primary, registry)

    assert issues == []
    assert [c.name for c in primary["body"].parameters[0].children] == ["chosen"]


def test_a_broken_type_reference_does_not_fall_through_to_the_description() -> None:
    """A type-cell anchor that resolves to nothing is a defect and is reported.
    Quietly using the description instead would hide it, and would attach
    children the row never asked for."""
    primary = {"body": _extraction([(_obj("a"), "missing", ("from_description",))])}
    registry = {"from_description": _table((_str("x"), None))}

    issues = resolve_nested(primary, registry)

    assert [i.code for i in issues] == [IssueCode.NESTED_TABLE_NOT_FOUND]
    assert primary["body"].parameters[0].children == []


def test_a_parent_name_label_wins_over_the_description() -> None:
    """The legacy label is matched before the description, so a document that
    resolved by label keeps resolving by label."""
    primary = {"body": _extraction([_described(_obj("firewall"), "from_description")])}
    registry = {"from_description": _table((_str("ignored"), None))}
    labels = {"firewall": _table((_str("chosen"), None)).table}

    issues = resolve_nested(primary, registry, label_tables=labels)

    assert issues == []
    assert [c.name for c in primary["body"].parameters[0].children] == ["chosen"]


def test_a_description_link_to_a_non_table_is_ignored() -> None:
    """Status codes, error codes and neighbouring pages are what descriptions
    link to most of the time. None of them is a structure."""
    primary = {"body": _extraction([_described(_obj("a"), "status_codes")])}
    registry = {"status_codes": RefTarget(kind=RefKind.NON_TABLE)}

    issues = resolve_nested(primary, registry)

    assert issues == []
    assert primary["body"].parameters[0].children == []


def test_an_unknown_description_link_is_ignored() -> None:
    primary = {"body": _extraction([_described(_obj("a"), "never_registered")])}

    assert resolve_nested(primary, {}) == []
    assert primary["body"].parameters[0].children == []


def test_two_candidate_tables_in_one_description_resolve_to_neither() -> None:
    """Nothing in the cell says which structure belongs to this row, and
    picking one would attach the other row's fields half the time."""
    primary = {"body": _extraction([_described(_obj("a"), "first", "second")])}
    registry = {
        "first": _table((_str("x"), None)),
        "second": _table((_str("y"), None)),
    }

    issues = resolve_nested(primary, registry)

    assert issues == []
    assert primary["body"].parameters[0].children == []


def test_one_table_among_several_links_still_resolves() -> None:
    """Only structure tables are candidates, so the usual mix of one table ref
    and a page link is not ambiguous."""
    primary = {"body": _extraction([_described(_obj("a"), "codes", "struct", "page")])}
    registry = {
        "codes": RefTarget(kind=RefKind.NON_TABLE),
        "struct": _table((_str("x"), None)),
        "page": RefTarget(kind=RefKind.NON_TABLE),
    }

    issues = resolve_nested(primary, registry)

    assert issues == []
    assert [c.name for c in primary["body"].parameters[0].children] == ["x"]


def test_a_description_reference_on_a_primitive_is_ignored() -> None:
    """A string does not hold children whatever its description links to."""
    primary = {"body": _extraction([_described(_str("name"), "struct")])}
    registry = {"struct": _table((_str("x"), None))}

    issues = resolve_nested(primary, registry)

    assert issues == []
    assert primary["body"].parameters[0].children == []


def test_a_nested_row_resolves_from_its_own_description() -> None:
    """The candidates travel with the row into recursion, so a struct table's
    own rows can carry them too."""
    inner = _table((_str("key"), None))
    outer = RefTarget(
        kind=RefKind.TABLE,
        table=_extraction([_described(_obj("tags"), "inner")]),
    )
    primary = {"body": _extraction([(_obj("firewall"), "outer", ())])}

    issues = resolve_nested(primary, {"outer": outer, "inner": inner})

    assert issues == []
    tags = primary["body"].parameters[0].children[0]
    assert [c.name for c in tags.children] == ["key"]
