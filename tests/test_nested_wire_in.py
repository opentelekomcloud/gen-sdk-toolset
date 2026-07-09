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
from tools.shared.report import IssueCode, SectionStatus


@pytest.fixture
def parser() -> DocutilsParser:
    return DocutilsParser()


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
    return [i.code for i in parsed.sections["body"].issues]


# --------------------------------------------------------------------------- #
# Happy path — VPC recursive chain
# --------------------------------------------------------------------------- #
def test_vpc_request_resolves_recursively(parser: DocutilsParser, vpc_doc: str) -> None:
    body = parser.parse(vpc_doc, "vpc.rst").sections["body"]
    assert body.status is SectionStatus.OK  # everything resolved, no issues

    firewall = next(p for p in body.parameters if p.name == "firewall")
    assert firewall.type_name == "CreateFirewallOption"
    child_names = {c.name for c in firewall.children}
    assert {"name", "tags", "admin_state_up"} <= child_names

    tags = next(c for c in firewall.children if c.name == "tags")
    assert [g.name for g in tags.children] == ["key", "value"]  # RequestTag


def test_vpc_response_resolves_recursively(
    parser: DocutilsParser, vpc_doc: str
) -> None:
    resp = parser.parse(vpc_doc, "vpc.rst").sections["response"]
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
    req_policy = next(
        p for p in parsed.sections["body"].parameters if p.name == "protect_policy"
    )
    resp_policy = next(
        p for p in parsed.sections["response"].parameters if p.name == "protect_policy"
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

    assert parsed.sections["body"].status is SectionStatus.OK
    assert parsed.sections["response"].status is SectionStatus.OK


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
    assert parsed.sections["body"].status is SectionStatus.PARTIAL
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
    assert parsed.sections["body"].status is SectionStatus.PARTIAL
    assert IssueCode.NESTED_CIRCULAR_REF in _body_issue_codes(parser, content)
    # First level resolved; recursion stopped at the repeat.
    node = parsed.sections["body"].parameters[0]
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
    assert parsed.sections["body"].status is SectionStatus.PARTIAL
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
    assert parsed.sections["body"].status is SectionStatus.PARTIAL
    assert IssueCode.NESTED_TABLE_EMPTY in _body_issue_codes(parser, content)


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
    assert parsed.sections["body"].status is SectionStatus.PARTIAL
    assert IssueCode.NESTED_REF_EXTERNAL in _body_issue_codes(parser, content)
