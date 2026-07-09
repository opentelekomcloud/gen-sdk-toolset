"""S4 (#28): the parser preserves ref anchors and captures ``type_name``.

The passthrough role now attaches the ``:ref:`` target to its inline node,
and ``extract_parameter_table`` records, per row, the struct anchor
(``ref_anchors``, aligned 1:1 with ``parameters``) and the visible struct
name (``Parameter.type_name``). Report-visible cell text is unchanged.
"""

from __future__ import annotations

import pytest
from docutils import nodes
from docutils.core import publish_doctree

from tools.scanner.parsers.docutils.doc_parser import _ensure_roles
from tools.scanner.parsers.docutils.table import (
    _struct_type_name,
    extract_parameter_table,
)
from tools.shared.ir import ParameterType

from .conftest import load_fixture


def _tables_by_title(content: str) -> dict[str, nodes.table]:
    """Map each ``.. table::`` title to its docutils node for a fixture."""
    _ensure_roles()
    doctree = publish_doctree(content, settings_overrides={"report_level": 5})
    out: dict[str, nodes.table] = {}
    for table in doctree.findall(nodes.table):
        title = next(iter(table.findall(nodes.title)), None)
        if title is not None:
            out[title.astext()] = table
    return out


# --------------------------------------------------------------------------- #
# VPC — anchor on the TYPE cell
# --------------------------------------------------------------------------- #
def test_vpc_request_body_type_cell_anchor() -> None:
    tables = _tables_by_title(load_fixture("style_a_vpc_with_refs.rst"))
    ex = extract_parameter_table(tables["Table 2 Request body parameters"])

    assert len(ex.ref_anchors) == len(ex.parameters)
    by_name = {p.name: (p, a) for p, a in zip(ex.parameters, ex.ref_anchors)}

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
    by_name = {p.name: (p, a) for p, a in zip(ex.parameters, ex.ref_anchors)}

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
    by_name = {p.name: (p, a) for p, a in zip(ex.parameters, ex.ref_anchors)}

    policy, anchor = by_name["protect_policy"]
    assert policy.param_type is ParameterType.OBJECT
    # Bare "object" carries no visible struct name...
    assert policy.type_name is None
    # ...but the name-cell ref anchor is still captured for resolution.
    assert anchor == "iam_02_0021__table54451161197"


def test_iam_named_object_anchor_on_name_cell() -> None:
    tables = _tables_by_title(load_fixture("style_a_iam_ref_in_param.rst"))
    ex = extract_parameter_table(tables["Table 4 protect_policy"])
    by_name = {p.name: (p, a) for p, a in zip(ex.parameters, ex.ref_anchors)}

    allow_user, anchor = by_name["allow_user"]
    assert allow_user.param_type is ParameterType.OBJECT
    assert allow_user.type_name == "AllowUserBody"
    assert anchor == "iam_02_0021__table744064115287"


# --------------------------------------------------------------------------- #
# Invariant
# --------------------------------------------------------------------------- #
def test_ref_anchors_aligned_with_parameters_across_fixtures() -> None:
    for fixture in (
        "style_a_vpc_with_refs.rst",
        "style_a_iam_ref_in_param.rst",
        "style_a_cce_grid.rst",
    ):
        for table in _tables_by_title(load_fixture(fixture)).values():
            ex = extract_parameter_table(table)
            assert len(ex.ref_anchors) == len(ex.parameters)


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
    assert _struct_type_name(raw_type) == expected
