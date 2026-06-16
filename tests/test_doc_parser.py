"""End-to-end tests for DocutilsParser against real OTC fixtures."""

from __future__ import annotations

import pytest

from tools.domain.ir import HttpMethod, ParameterType
from tools.domain.report import IssueCode, ParseFailure, SectionStatus
from tools.infrastructure.parsers import DocutilsParser


@pytest.fixture
def parser() -> DocutilsParser:
    return DocutilsParser()


# --------------------------------------------------------------------------- #
# CCE — modern grid tables, simple :ref: targets, request header + body
# --------------------------------------------------------------------------- #
def test_cce_gating(parser: DocutilsParser, cce_doc: str) -> None:
    parsed = parser.parse(cce_doc, "fixtures/cce.rst")
    assert parsed.method is HttpMethod.PUT
    assert parsed.uri == (
        "/api/v3/projects/{project_id}/clusters/{cluster_id}/nodes/{node_id}"
    )
    assert parsed.title == "Updating a Specified Node"
    assert parsed.api_version == "v3"


def test_cce_path_params(parser: DocutilsParser, cce_doc: str) -> None:
    parsed = parser.parse(cce_doc, "fixtures/cce.rst")
    sec = parsed.sections["path_params"]
    assert sec.status is SectionStatus.OK
    names = [p.name for p in sec.parameters]
    assert names == ["project_id", "cluster_id", "node_id"]
    assert all(p.mandatory for p in sec.parameters)


def test_cce_body_excludes_struct_table(parser: DocutilsParser, cce_doc: str) -> None:
    """The 'Data structure of metadata field' table should NOT be merged
    into the body — only the top-level body table contributes."""
    parsed = parser.parse(cce_doc, "fixtures/cce.rst")
    sec = parsed.sections["body"]
    names = [p.name for p in sec.parameters]
    assert names == ["metadata"]
    assert sec.parameters[0].param_type is ParameterType.OBJECT


def test_cce_headers(parser: DocutilsParser, cce_doc: str) -> None:
    parsed = parser.parse(cce_doc, "fixtures/cce.rst")
    sec = parsed.sections["headers"]
    names = [p.name for p in sec.parameters]
    assert "X-Auth-Token" in names
    assert "Content-Type" in names


# --------------------------------------------------------------------------- #
# VPC — newer Style A with Definition/Constraints/Range in description cells
# --------------------------------------------------------------------------- #
def test_vpc_gating(parser: DocutilsParser, vpc_doc: str) -> None:
    parsed = parser.parse(vpc_doc, "fixtures/vpc.rst")
    assert parsed.method is HttpMethod.POST
    assert parsed.uri == "/v3/{project_id}/vpc/firewalls"
    assert parsed.api_version == "v3"


def test_vpc_body_top_level_only(parser: DocutilsParser, vpc_doc: str) -> None:
    """Body has just firewall + dry_run; CreateFirewallOption is a
    struct definition (nested_struct) and must not inflate the body."""
    parsed = parser.parse(vpc_doc, "fixtures/vpc.rst")
    sec = parsed.sections["body"]
    names = [p.name for p in sec.parameters]
    assert names == ["firewall", "dry_run"]


def test_vpc_response_top_level_only(parser: DocutilsParser, vpc_doc: str) -> None:
    parsed = parser.parse(vpc_doc, "fixtures/vpc.rst")
    sec = parsed.sections["response"]
    names = [p.name for p in sec.parameters]
    assert names == ["firewall", "request_id"]


def test_vpc_has_examples(parser: DocutilsParser, vpc_doc: str) -> None:
    parsed = parser.parse(vpc_doc, "fixtures/vpc.rst")
    assert len(parsed.sections["example_request"].examples) >= 1
    assert len(parsed.sections["example_response"].examples) >= 1


# --------------------------------------------------------------------------- #
# KMS — simple `=== ===` tables + bulleted Example section
# --------------------------------------------------------------------------- #
def test_kms_simple_table(parser: DocutilsParser, kms_doc: str) -> None:
    parsed = parser.parse(kms_doc, "fixtures/kms.rst")
    sec = parsed.sections["body"]
    names = [p.name for p in sec.parameters]
    assert names == ["key_id", "grant_id", "sequence"]
    assert sec.parameters[0].mandatory is True
    assert sec.parameters[2].mandatory is False  # sequence is optional


def test_kms_bulleted_examples(parser: DocutilsParser, kms_doc: str) -> None:
    """The combined 'Example' section splits bullets by label
    (-  Example request / -  Example response)."""
    parsed = parser.parse(kms_doc, "fixtures/kms.rst")
    assert "example_request" in parsed.sections
    assert "example_response" in parsed.sections
    # At least one response example is valid JSON parsed
    req = parsed.sections["example_request"].examples[0]
    assert req.raw  # non-empty
    assert req.parsed is not None  # JSON should parse
    assert "key_id" in req.parsed


# --------------------------------------------------------------------------- #
# IAM — :ref: in the Parameter column rather than the Type column
# --------------------------------------------------------------------------- #
def test_iam_strips_ref_in_name(parser: DocutilsParser, iam_doc: str) -> None:
    parsed = parser.parse(iam_doc, "fixtures/iam.rst")
    sec = parsed.sections["body"]
    # parameter name should be the visible label, with :ref: markup stripped
    assert sec.parameters[0].name == "protect_policy"


# --------------------------------------------------------------------------- #
# Behavioural — gating failure
# --------------------------------------------------------------------------- #
def test_no_uri_raises(parser: DocutilsParser) -> None:
    content = """
Some Page
=========

This page has no URI line.
"""
    with pytest.raises(ParseFailure) as excinfo:
        parser.parse(content, "missing-uri.rst")
    assert excinfo.value.issue.code is IssueCode.NO_URI_MATCH


# --------------------------------------------------------------------------- #
# ELB list endpoint — path vs query parameter separation
# --------------------------------------------------------------------------- #
def test_elb_list_separates_path_and_query(
    parser: DocutilsParser, elb_list_doc: str
) -> None:
    parsed = parser.parse(elb_list_doc, "fixtures/elb.rst")

    # Host-form URI is recognised and stored without the host.
    assert parsed.method is HttpMethod.GET
    assert parsed.uri == "/v3/{project_id}/elb/pools"

    path_names = [p.name for p in parsed.sections["path_params"].parameters]
    query_names = [p.name for p in parsed.sections["query_params"].parameters]

    assert path_names == ["project_id"]
    assert query_names == ["marker", "limit", "page_reverse"]

    # The pagination params must NOT have leaked into path_params.
    assert "limit" not in path_names
    assert "marker" not in path_names


def test_elb_query_section_present(parser: DocutilsParser, elb_list_doc: str) -> None:
    parsed = parser.parse(elb_list_doc, "fixtures/elb.rst")
    assert "query_params" in parsed.sections


# --------------------------------------------------------------------------- #
# Quality-report shape sanity
# --------------------------------------------------------------------------- #
def test_field_metrics_sum(parser: DocutilsParser, vpc_doc: str) -> None:
    """fields_recognized + fields_unknown_type + fields_failed == fields_total."""
    parsed = parser.parse(vpc_doc, "fixtures/vpc.rst")
    for sec in parsed.sections.values():
        assert (
            sec.fields_recognized + sec.fields_unknown_type + sec.fields_failed
            == sec.fields_total
        )


# --------------------------------------------------------------------------- #
# Canonical-key guard
# --------------------------------------------------------------------------- #
def test_parser_section_keys_are_canonical(
    parser: DocutilsParser,
    cce_doc: str,
    vpc_doc: str,
    kms_doc: str,
    iam_doc: str,
    elb_list_doc: str,
) -> None:
    from tools.domain.report import SECTION_NAMES

    docs = {
        "cce.rst": cce_doc,
        "vpc.rst": vpc_doc,
        "kms.rst": kms_doc,
        "iam.rst": iam_doc,
        "elb.rst": elb_list_doc,
    }
    produced: set[str] = set()
    for path, content in docs.items():
        produced.update(parser.parse(content, path).sections)

    assert produced, "fixtures should exercise at least one section"
    off_canon = produced - set(SECTION_NAMES)
    assert not off_canon, f"parser produced non-canonical section keys: {off_canon}"
