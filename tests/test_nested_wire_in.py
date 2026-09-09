"""S6 (#30): end-to-end nested-struct resolution through the parser.

Covers the happy paths on real fixtures (VPC recursive chain; IAM same-named
request/response structs that must bind to their own tables by anchor) and one
fixture per failure code — NESTED_TABLE_NOT_FOUND, NESTED_CIRCULAR_REF,
NESTED_REF_NOT_A_TABLE, NESTED_TABLE_EMPTY, and NESTED_REF_EXTERNAL (an anchor
whose docid differs from the document's own label).
"""

from __future__ import annotations

import pytest

from tools.scanner.parsers import DocutilsParser
from tools.shared.scan import IssueCode, SectionStatus


@pytest.fixture
def parser() -> DocutilsParser:
    return DocutilsParser()


def _sections(parsed) -> dict:
    return {section.name: section for section in parsed.sections}


# --------------------------------------------------------------------------- #
# Minimal-doc builders (programmatic so column alignment is always valid)
# --------------------------------------------------------------------------- #
def _simple_table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    cols = list(zip(*([headers] + rows)))
    widths = [max(len(cell) for cell in col) for col in cols]
    bar = "  ".join("=" * w for w in widths)

    def fmt(cells: list[str]) -> str:
        return "  ".join(cell.ljust(w) for cell, w in zip(cells, widths))

    lines = [bar, fmt(headers), bar, *[fmt(r) for r in rows], bar]
    indented = "\n".join("   " + ln for ln in lines)
    return f".. table:: {title}\n\n{indented}\n"


def _doc(*blocks: str, doc_label: str | None = None) -> str:
    # An optional `.. _<doc_label>:` before the title gives the doc its own
    # docid, needed to tell cross-doc refs from in-doc ones. The
    # `:original_name:` docinfo mirrors real OTC docs and keeps the lone title
    # from being promoted to the document title, so the docid (and title name)
    # land on the top section — where the parser reads them.
    prefix = f":original_name: demo.html\n\n.. _{doc_label}:\n\n" if doc_label else ""
    head = (
        f"{prefix}Demo\n====\n\nURI\n---\n\nPOST /v1/test\n\n"
        "Request Parameters\n------------------\n\n"
    )
    return head + "\n".join(blocks)


def _body_issue_codes(parser: DocutilsParser, content: str) -> list[IssueCode]:
    parsed = parser.parse(content, "x.rst")
    return [i.code for i in _sections(parsed)["body"].scan_result.issues]


# --------------------------------------------------------------------------- #
# Happy path — VPC recursive chain
# --------------------------------------------------------------------------- #
def test_vpc_request_resolves_recursively(parser: DocutilsParser, vpc_doc: str) -> None:
    body = _sections(parser.parse(vpc_doc, "vpc.rst"))["body"]
    assert body.scan_result.status is SectionStatus.OK

    firewall = next(p for p in body.parameters if p.name == "firewall")
    assert firewall.type_name == "CreateFirewallOption"
    child_names = {c.name for c in firewall.children}
    assert {"name", "tags", "admin_state_up"} <= child_names

    tags = next(c for c in firewall.children if c.name == "tags")
    assert [g.name for g in tags.children] == ["key", "value"]  # RequestTag


def test_vpc_response_resolves_recursively(
    parser: DocutilsParser, vpc_doc: str
) -> None:
    resp = _sections(parser.parse(vpc_doc, "vpc.rst"))["response"]
    firewall = next(p for p in resp.parameters if p.name == "firewall")
    detail = {c.name for c in firewall.children}
    assert {"tags", "associations", "ingress_rules", "egress_rules"} <= detail

    ingress = next(c for c in firewall.children if c.name == "ingress_rules")
    assert any(g.name == "action" for g in ingress.children)  # FirewallRuleDetail


# --------------------------------------------------------------------------- #
# Happy path — IAM same-named structs resolve by anchor (no name collision)
# --------------------------------------------------------------------------- #
def test_iam_same_named_structs_bind_to_their_own_tables(
    parser: DocutilsParser, iam_doc: str
) -> None:
    parsed = parser.parse(iam_doc, "iam.rst")
    sections = _sections(parsed)
    req_policy = next(
        p for p in sections["body"].parameters if p.name == "protect_policy"
    )
    resp_policy = next(
        p for p in sections["response"].parameters if p.name == "protect_policy"
    )

    req_fields = {c.name for c in req_policy.children}
    resp_fields = {c.name for c in resp_policy.children}
    # Request protect_policy (Table 4) has mobile/email; response (Table 7)
    # does not. Name-based linking would collide both onto one table; anchor-
    # based binds each to its own.
    assert {"mobile", "email"} <= req_fields
    assert "mobile" not in resp_fields and "email" not in resp_fields

    # Both nested allow_user structs resolve too (field-path-titled tables).
    req_allow = next(c for c in req_policy.children if c.name == "allow_user")
    resp_allow = next(c for c in resp_policy.children if c.name == "allow_user")
    assert {g.name for g in req_allow.children} == {
        "manage_accesskey",
        "manage_email",
        "manage_mobile",
        "manage_password",
    }
    assert resp_allow.children  # bound to Table 8, its own table

    assert sections["body"].scan_result.status is SectionStatus.OK
    assert sections["response"].scan_result.status is SectionStatus.OK


# --------------------------------------------------------------------------- #
# Failure codes — one minimal doc each, degrading body to PARTIAL
# --------------------------------------------------------------------------- #
def test_dangling_anchor(parser: DocutilsParser) -> None:
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["foo", ":ref:`Foo <nope_missing>` object", "a foo"]],
        )
    )
    parsed = parser.parse(content, "x.rst")
    assert _sections(parsed)["body"].scan_result.status is SectionStatus.PARTIAL
    assert IssueCode.NESTED_TABLE_NOT_FOUND in _body_issue_codes(parser, content)


def test_circular_ref(parser: DocutilsParser) -> None:
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["node", ":ref:`Node <node_struct>` object", "a node"]],
        ),
        ".. _node_struct:\n",
        _simple_table(
            "**Table 2** Node",
            ["Parameter", "Type", "Description"],
            [["child", ":ref:`Node <node_struct>` object", "self"]],
        ),
    )
    parsed = parser.parse(content, "x.rst")
    sections = _sections(parsed)
    assert sections["body"].scan_result.status is SectionStatus.PARTIAL
    assert IssueCode.NESTED_CIRCULAR_REF in _body_issue_codes(parser, content)
    # First level resolved; recursion stopped at the repeat.
    node = sections["body"].parameters[0]
    assert [c.name for c in node.children] == ["child"]
    assert node.children[0].children == []


def test_non_table_target(parser: DocutilsParser) -> None:
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["foo", ":ref:`Foo <foo_para>` object", "a foo"]],
        ),
        ".. _foo_para:\n\nThis paragraph is not a table.\n",
    )
    parsed = parser.parse(content, "x.rst")
    assert _sections(parsed)["body"].scan_result.status is SectionStatus.PARTIAL
    assert IssueCode.NESTED_REF_NOT_A_TABLE in _body_issue_codes(parser, content)


def test_empty_struct_table(parser: DocutilsParser) -> None:
    empty_table = (
        ".. _empty_struct:\n\n"
        ".. table:: **Table 2** Foo\n\n"
        "   +-----------+--------+\n"
        "   | Parameter | Type   |\n"
        "   +===========+========+\n"
        "   +-----------+--------+\n"
    )
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["foo", ":ref:`Foo <empty_struct>` object", "a foo"]],
        ),
        empty_table,
    )
    parsed = parser.parse(content, "x.rst")
    assert _sections(parsed)["body"].scan_result.status is SectionStatus.PARTIAL
    assert IssueCode.NESTED_TABLE_EMPTY in _body_issue_codes(parser, content)


def test_unreferenced_struct_table_is_reported(parser: DocutilsParser) -> None:
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["name", "String", "a name"]],
        ),
        ".. _unused_struct:\n",
        _simple_table(
            "**Table 2** Unused",
            ["Parameter", "Type", "Description"],
            [["value", "String", "a value"]],
        ),
    )

    body = _sections(parser.parse(content, "x.rst"))["body"]

    assert body.scan_result.status is SectionStatus.PARTIAL
    assert IssueCode.NESTED_PARENT_NOT_FOUND in _body_issue_codes(parser, content)


def test_external_cross_doc_ref(parser: DocutilsParser) -> None:
    # This doc's label is `thisdoc`; the ref's docid `otherdoc` differs, so it
    # points into another document -> external (not a dangling in-doc ref).
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["foo", ":ref:`Foo <otherdoc__struct>` object", "a foo"]],
        ),
        doc_label="thisdoc",
    )
    parsed = parser.parse(content, "x.rst")
    assert _sections(parsed)["body"].scan_result.status is SectionStatus.PARTIAL
    assert IssueCode.NESTED_REF_EXTERNAL in _body_issue_codes(parser, content)


def test_explicit_cross_document_field_table(parser: DocutilsParser) -> None:
    overview = "Overview\n========\n\n.. _connection_fields:\n\n" + _simple_table(
        "**Table 1** Connection fields",
        ["Parameter", "Type", "Description"],
        [["id", "String", "connection ID"], ["name", "String", "name"]],
    )
    endpoint = (
        "Demo\n====\n\nURI\n---\n\nGET /v1/test\n\n"
        "Response\n--------\n\n"
        + _simple_table(
            "**Table 1** Response parameters",
            ["Parameter", "Type", "Description"],
            [["connection", "Object", "connection object"]],
        )
        + "\nFor details about the **connection** field, "
        "see :ref:`Table 1 <connection_fields>`.\n"
    )

    context = parser.build_repository_context({"overview.rst": overview})
    response = _sections(parser.parse(endpoint, "endpoint.rst", context=context))[
        "response"
    ]

    connection = response.parameters[0]
    assert [child.name for child in connection.children] == ["id", "name"]
    assert response.scan_result.status is SectionStatus.OK


# --------------------------------------------------------------------------- #
# References written into the description cell
# --------------------------------------------------------------------------- #
def test_object_array_resolves_from_its_description(parser: DocutilsParser) -> None:
    """The common api-ref shape: the type cell says only `Array of objects`, and
    the structure is named by a `see Table 2` link in the description."""
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Mandatory", "Type", "Description"],
            [
                [
                    "tags",
                    "No",
                    "Array of objects",
                    "Bound tags. For details, see :ref:`Table 2 <tag_struct>`.",
                ]
            ],
        ),
        ".. _tag_struct:\n",
        _simple_table(
            "**Table 2** tags",
            ["Parameter", "Type", "Description"],
            [["key", "String", "tag key"], ["value", "String", "tag value"]],
        ),
    )

    body = _sections(parser.parse(content, "x.rst"))["body"]

    assert body.scan_result.status is SectionStatus.OK
    tags = body.parameters[0]
    assert [c.name for c in tags.children] == ["key", "value"]
    # The struct table is now claimed, so it is no longer an orphan.
    assert IssueCode.NESTED_PARENT_NOT_FOUND not in _body_issue_codes(parser, content)


def test_object_resolves_from_its_description(parser: DocutilsParser) -> None:
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["firewall", "Object", "See :ref:`Table 2 <fw_struct>` for details."]],
        ),
        ".. _fw_struct:\n",
        _simple_table(
            "**Table 2** firewall",
            ["Parameter", "Type", "Description"],
            [["name", "String", "a name"]],
        ),
    )

    body = _sections(parser.parse(content, "x.rst"))["body"]

    assert body.scan_result.status is SectionStatus.OK
    assert [c.name for c in body.parameters[0].children] == ["name"]


def test_a_status_code_link_in_a_description_is_not_a_structure(
    parser: DocutilsParser,
) -> None:
    """Descriptions link to status codes and neighbouring pages constantly. The
    parameter keeps no children, and the link raises nothing."""
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["config", "Object", "See :ref:`Status Codes <codes_para>`."]],
        ),
        ".. _codes_para:\n\nThis paragraph is not a table.\n",
    )

    body = _sections(parser.parse(content, "x.rst"))["body"]

    assert body.parameters[0].children == []
    assert IssueCode.NESTED_REF_NOT_A_TABLE not in _body_issue_codes(parser, content)


def test_the_type_cell_still_wins_over_the_description(
    parser: DocutilsParser,
) -> None:
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [
                [
                    "firewall",
                    ":ref:`Chosen <chosen_struct>` object",
                    "See also :ref:`Table 3 <other_struct>`.",
                ]
            ],
        ),
        ".. _chosen_struct:\n",
        _simple_table(
            "**Table 2** Chosen",
            ["Parameter", "Type", "Description"],
            [["chosen", "String", "from the type cell"]],
        ),
        ".. _other_struct:\n",
        _simple_table(
            "**Table 3** Other",
            ["Parameter", "Type", "Description"],
            [["ignored", "String", "from the description"]],
        ),
    )

    body = _sections(parser.parse(content, "x.rst"))["body"]

    assert [c.name for c in body.parameters[0].children] == ["chosen"]


def test_the_name_cell_still_wins_over_the_description(
    parser: DocutilsParser,
) -> None:
    """The middle step of the priority: no ref in the type cell, one in the
    name cell, one in the description. The name cell decides."""
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [
                [
                    ":ref:`firewall <named_struct>`",
                    "Object",
                    "See also :ref:`Table 3 <desc_struct>`.",
                ]
            ],
        ),
        ".. _named_struct:\n",
        _simple_table(
            "**Table 2** Named",
            ["Parameter", "Type", "Description"],
            [["chosen", "String", "from the name cell"]],
        ),
        ".. _desc_struct:\n",
        _simple_table(
            "**Table 3** Described",
            ["Parameter", "Type", "Description"],
            [["ignored", "String", "from the description"]],
        ),
    )

    body = _sections(parser.parse(content, "x.rst"))["body"]

    assert [c.name for c in body.parameters[0].children] == ["chosen"]


def test_two_structure_links_in_one_description_resolve_to_neither(
    parser: DocutilsParser,
) -> None:
    """Both tables stay unclaimed and are reported as such, which is the same
    account of them the scanner gave before descriptions were read at all."""
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [
                [
                    "thing",
                    "Object",
                    "See :ref:`Table 2 <a_struct>` and :ref:`Table 3 <b_struct>`.",
                ]
            ],
        ),
        ".. _a_struct:\n",
        _simple_table(
            "**Table 2** A",
            ["Parameter", "Type", "Description"],
            [["a", "String", "a"]],
        ),
        ".. _b_struct:\n",
        _simple_table(
            "**Table 3** B",
            ["Parameter", "Type", "Description"],
            [["b", "String", "b"]],
        ),
    )

    body = _sections(parser.parse(content, "x.rst"))["body"]

    assert body.parameters[0].children == []
    assert IssueCode.NESTED_PARENT_NOT_FOUND in _body_issue_codes(parser, content)


def test_a_link_to_the_primary_table_is_not_a_structure(
    parser: DocutilsParser,
) -> None:
    """Only tables routed as nested structs are registered, so a description
    pointing back at the request table itself resolves to nothing rather than
    attaching the whole table to one of its own rows."""
    content = _doc(
        ".. _own_table:\n",
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["cfg", "Object", "See :ref:`Table 1 <own_table>`."]],
        ),
    )

    body = _sections(parser.parse(content, "x.rst"))["body"]

    assert body.parameters[0].children == []
    assert body.scan_result.status is SectionStatus.OK


def test_a_cycle_through_descriptions_terminates(parser: DocutilsParser) -> None:
    """Description candidates go through the same `visiting` check as authored
    anchors, so a structure whose own description points back at itself stops
    and is reported instead of recursing."""
    content = _doc(
        _simple_table(
            "**Table 1** Request body parameters",
            ["Parameter", "Type", "Description"],
            [["a", "Object", "See :ref:`Table 2 <a_struct>`."]],
        ),
        ".. _a_struct:\n",
        _simple_table(
            "**Table 2** A",
            ["Parameter", "Type", "Description"],
            [["back", "Object", "See :ref:`Table 2 <a_struct>`."]],
        ),
    )
    parsed = parser.parse(content, "x.rst")
    body = _sections(parsed)["body"]

    assert IssueCode.NESTED_CIRCULAR_REF in _body_issue_codes(parser, content)
    # First level resolved; recursion stopped at the repeat.
    assert [c.name for c in body.parameters[0].children] == ["back"]
    assert body.parameters[0].children[0].children == []
