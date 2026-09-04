"""S4 (#28): the parser preserves ref anchors and captures ``type_name``.

The passthrough role attaches the ``:ref:`` target to its inline node, and
``extract_parameter_table`` keeps that anchor in the same row as the parsed
parameter. Report-visible cell text is unchanged.
"""

from __future__ import annotations

import pytest
from docutils import nodes
from docutils.core import publish_doctree

from tools.scanner.parsers.docutils.context import ensure_roles
from tools.scanner.parsers.docutils.field_type import extract_struct_type_name
from tools.scanner.parsers.docutils.table import (
    ExtractionMetrics,
    TableExtraction,
    TableRow,
    extract_parameter_table,
)
from tools.shared.ir import Parameter, ParameterType

from .conftest import load_fixture


def _tables_by_title(content: str) -> dict[str, nodes.table]:
    """Map each ``.. table::`` title to its docutils node for a fixture."""
    ensure_roles()
    doctree = publish_doctree(content, settings_overrides={"report_level": 5})
    out: dict[str, nodes.table] = {}
    for table in doctree.findall(nodes.table):
        title = next(iter(table.findall(nodes.title)), None)
        if title is not None:
            out[title.astext()] = table
    return out


def _rows_by_name(extraction):
    return {
        row.parameter.name: (row.parameter, row.ref_anchor) for row in extraction.rows
    }


def test_table_extraction_extends_complete_rows() -> None:
    first = TableExtraction(
        rows=[TableRow(Parameter(name="first"), "first_anchor")],
        issues=[],
        metrics=ExtractionMetrics(
            fields_total=1, fields_recognized=1, fields_unknown_type=0, fields_failed=0
        ),
    )
    second = TableExtraction(
        rows=[TableRow(Parameter(name="second"), "second_anchor")],
        issues=[],
        metrics=ExtractionMetrics(
            fields_total=1, fields_recognized=1, fields_unknown_type=0, fields_failed=0
        ),
    )

    first.extend(second)

    assert [(row.parameter.name, row.ref_anchor) for row in first.rows] == [
        ("first", "first_anchor"),
        ("second", "second_anchor"),
    ]
    assert first.metrics.fields_total == 2
    assert first.metrics.fields_recognized == 2


# --------------------------------------------------------------------------- #
# VPC — anchor on the TYPE cell
# --------------------------------------------------------------------------- #
def test_vpc_request_body_type_cell_anchor() -> None:
    tables = _tables_by_title(load_fixture("style_a_vpc_with_refs.rst"))
    ex = extract_parameter_table(tables["Table 2 Request body parameters"])

    by_name = _rows_by_name(ex)

    firewall, firewall_anchor = by_name["firewall"]
    assert firewall.param_type is ParameterType.OBJECT
    assert firewall.type_name == "CreateFirewallOption"
    assert firewall_anchor == "createfirewall__request_createfirewalloption"

    # Primitive row: no anchor, no type_name, label preserved.
    dry_run, dry_run_anchor = by_name["dry_run"]
    assert dry_run.param_type is ParameterType.BOOLEAN
    assert dry_run.type_name is None
    assert dry_run_anchor is None


def test_vpc_array_of_objects_anchor() -> None:
    tables = _tables_by_title(load_fixture("style_a_vpc_with_refs.rst"))
    ex = extract_parameter_table(tables["Table 3 CreateFirewallOption"])
    by_name = _rows_by_name(ex)

    tags, tags_anchor = by_name["tags"]
    assert tags.param_type is ParameterType.ARRAY_OF_OBJECTS
    assert tags.type_name == "RequestTag"
    assert tags_anchor == "createfirewall__request_requesttag"

    # A plain String field stays primitive.
    name_param, name_anchor = by_name["name"]
    assert name_param.type_name is None
    assert name_anchor is None


# --------------------------------------------------------------------------- #
# IAM — anchor on the NAME cell, bare "object" type
# --------------------------------------------------------------------------- #
def test_iam_name_cell_anchor_bare_object() -> None:
    tables = _tables_by_title(load_fixture("style_a_iam_ref_in_param.rst"))
    ex = extract_parameter_table(tables["Table 3 Parameters in the request body"])
    by_name = _rows_by_name(ex)

    policy, anchor = by_name["protect_policy"]
    assert policy.param_type is ParameterType.OBJECT
    # Bare "object" carries no visible struct name...
    assert policy.type_name is None
    # ...but the name-cell ref anchor is still captured for resolution.
    assert anchor == "iam_02_0021__table54451161197"


def test_iam_named_object_anchor_on_name_cell() -> None:
    tables = _tables_by_title(load_fixture("style_a_iam_ref_in_param.rst"))
    ex = extract_parameter_table(tables["Table 4 protect_policy"])
    by_name = _rows_by_name(ex)

    allow_user, anchor = by_name["allow_user"]
    assert allow_user.param_type is ParameterType.OBJECT
    assert allow_user.type_name == "AllowUserBody"
    assert anchor == "iam_02_0021__table744064115287"


# --------------------------------------------------------------------------- #
# Struct-name extraction, including irregular whitespace
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw_type, expected",
    [
        ("CreateFirewallOption object", "CreateFirewallOption"),
        ("Array of RequestTag objects", "RequestTag"),
        ("AllowUserBody object", "AllowUserBody"),
        # Keyword-only cells carry no struct name.
        ("object", None),
        ("Array of objects", None),
        # Irregular whitespace in "array of" and around the name must still
        # yield the bare struct name.
        ("Array  of  RequestTag  objects", "RequestTag"),
        ("Array\nof\nRequestTag objects", "RequestTag"),
        ("  Array of   RequestTag  ", "RequestTag"),
    ],
)
def test_struct_type_name(raw_type: str, expected: str | None) -> None:
    assert extract_struct_type_name(raw_type) == expected


# --------------------------------------------------------------------------- #
# Description-cell refs are captured as candidates, not as anchors
# --------------------------------------------------------------------------- #
HEADERS = ["Parameter", "Mandatory", "Type", "Description"]


def _extract(*rows: list[str]) -> dict[str, TableRow]:
    """Parse a parameter table built from `rows`, indexed by parameter name.

    Built rather than written out, so the column rules always match the widest
    cell - a description carrying two refs is long enough to break a hand-drawn
    grid, and docutils answers that with a malformed-table error, not a row.
    """
    ensure_roles()
    widths = [max(len(c) for c in col) for col in zip(*([HEADERS] + list(rows)))]
    bar = "  ".join("=" * w for w in widths)
    lines = [
        bar,
        *("  ".join(c.ljust(w) for c, w in zip(r, widths)) for r in [HEADERS, *rows]),
        bar,
    ]
    lines.insert(2, bar)
    doctree = publish_doctree(
        "\n".join(lines) + "\n", settings_overrides={"report_level": 5}
    )
    table = next(iter(doctree.findall(nodes.table)))
    return {row.parameter.name: row for row in extract_parameter_table(table).rows}


def test_a_description_ref_is_kept_apart_from_the_anchor() -> None:
    """It lands in `description_anchors`, never in `ref_anchor`: the resolver
    treats the two differently, and collapsing them would make a stray link in
    prose look like an authored struct reference."""
    row = _extract(
        ["tags", "No", "Array of objects", "See :ref:`T2 <tag_struct>` for details."]
    )["tags"]

    assert row.ref_anchor is None
    assert row.description_anchors == ("tag_struct",)


def test_every_description_ref_is_kept_in_the_order_written() -> None:
    row = _extract(["thing", "No", "Object", "See :ref:`A <a_s>` and :ref:`B <b_s>`."])[
        "thing"
    ]

    assert row.description_anchors == ("a_s", "b_s")


def test_the_same_ref_written_twice_is_one_candidate() -> None:
    """Prose repeats itself. Counting the repeat would make one structure look
    like two and leave the row unresolved for a reason the page never gave."""
    row = _extract(
        [
            "thing",
            "No",
            "Object",
            "See :ref:`A <a_s>`, described in :ref:`A <a_s>`.",
        ]
    )["thing"]

    assert row.description_anchors == ("a_s",)


def test_a_primitive_row_collects_no_description_refs() -> None:
    """Nothing that cannot hold children needs candidates, so its description is
    not walked at all - the same gate that already decides `ref_anchor`."""
    row = _extract(["name", "No", "String", "See :ref:`Codes <codes>`."])["name"]

    assert row.ref_anchor is None
    assert row.description_anchors == ()
