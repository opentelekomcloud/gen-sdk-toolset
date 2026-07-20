"""End-to-end tests for DocutilsParser against real OTC fixtures."""

from __future__ import annotations

import pytest

from tools.scanner.parsers import DocutilsParser
from tools.shared.exceptions import ParseFailure
from tools.shared.ir import Example, HttpMethod, ParameterType, SectionName
from tools.shared.scan import IssueCode, SectionStatus


@pytest.fixture
def parser() -> DocutilsParser:
    return DocutilsParser()


def _sections(parsed) -> dict:
    return {section.name: section for section in parsed.sections}


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
    sec = _sections(parsed)["path_params"]
    assert sec.scan_result.status is SectionStatus.OK
    names = [p.name for p in sec.parameters]
    assert names == ["project_id", "cluster_id", "node_id"]
    assert all(p.mandatory for p in sec.parameters)


def test_cce_body_excludes_struct_table(parser: DocutilsParser, cce_doc: str) -> None:
    """The 'Data structure of metadata field' table should NOT be merged
    into the body — only the top-level body table contributes."""
    parsed = parser.parse(cce_doc, "fixtures/cce.rst")
    sec = _sections(parsed)["body"]
    names = [p.name for p in sec.parameters]
    assert names == ["metadata"]
    assert sec.parameters[0].param_type is ParameterType.OBJECT


def test_cce_headers(parser: DocutilsParser, cce_doc: str) -> None:
    parsed = parser.parse(cce_doc, "fixtures/cce.rst")
    sec = _sections(parsed)["headers"]
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
    sec = _sections(parsed)["body"]
    names = [p.name for p in sec.parameters]
    assert names == ["firewall", "dry_run"]


def test_vpc_response_top_level_only(parser: DocutilsParser, vpc_doc: str) -> None:
    parsed = parser.parse(vpc_doc, "fixtures/vpc.rst")
    sec = _sections(parsed)["response"]
    names = [p.name for p in sec.parameters]
    assert names == ["firewall", "request_id"]


def test_vpc_has_examples(parser: DocutilsParser, vpc_doc: str) -> None:
    parsed = parser.parse(vpc_doc, "fixtures/vpc.rst")
    sections = _sections(parsed)
    assert len(sections["example_request"].examples) >= 1
    assert len(sections["example_response"].examples) >= 1


# --------------------------------------------------------------------------- #
# KMS — simple `=== ===` tables + bulleted Example section
# --------------------------------------------------------------------------- #
def test_kms_simple_table(parser: DocutilsParser, kms_doc: str) -> None:
    parsed = parser.parse(kms_doc, "fixtures/kms.rst")
    sec = _sections(parsed)["body"]
    names = [p.name for p in sec.parameters]
    assert names == ["key_id", "grant_id", "sequence"]
    assert sec.parameters[0].mandatory is True
    assert sec.parameters[2].mandatory is False


def test_kms_bulleted_examples(parser: DocutilsParser, kms_doc: str) -> None:
    """The combined 'Example' section splits bullets by label
    (-  Example request / -  Example response)."""
    parsed = parser.parse(kms_doc, "fixtures/kms.rst")
    sections = _sections(parsed)
    assert "example_request" in sections
    assert "example_response" in sections
    req = sections["example_request"].examples[0]
    assert req.raw
    assert req.parsed is not None
    assert "key_id" in req.parsed


# --------------------------------------------------------------------------- #
# IAM — :ref: in the Parameter column rather than the Type column
# --------------------------------------------------------------------------- #
def test_iam_strips_ref_in_name(parser: DocutilsParser, iam_doc: str) -> None:
    parsed = parser.parse(iam_doc, "fixtures/iam.rst")
    sec = _sections(parsed)["body"]
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

    sections = _sections(parsed)
    path_names = [p.name for p in sections["path_params"].parameters]
    query_names = [p.name for p in sections["query_params"].parameters]

    assert path_names == ["project_id"]
    assert query_names == ["marker", "limit", "page_reverse"]

    # The pagination params must NOT have leaked into path_params.
    assert "limit" not in path_names
    assert "marker" not in path_names


def test_elb_query_section_present(parser: DocutilsParser, elb_list_doc: str) -> None:
    parsed = parser.parse(elb_list_doc, "fixtures/elb.rst")
    assert "query_params" in _sections(parsed)


# --------------------------------------------------------------------------- #
# Quality-report shape sanity
# --------------------------------------------------------------------------- #
def test_field_metrics_sum(parser: DocutilsParser, vpc_doc: str) -> None:
    """fields_recognized + fields_unknown_type + fields_failed == fields_total."""
    parsed = parser.parse(vpc_doc, "fixtures/vpc.rst")
    for section in parsed.sections:
        result = section.scan_result
        assert (
            result.fields_recognized + result.fields_unknown_type + result.fields_failed
            == result.fields_total
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
    docs = {
        "cce.rst": cce_doc,
        "vpc.rst": vpc_doc,
        "kms.rst": kms_doc,
        "iam.rst": iam_doc,
        "elb.rst": elb_list_doc,
    }
    for path, content in docs.items():
        parsed = parser.parse(content, path)
        produced = {section.name for section in parsed.sections}
        assert produced == set(SectionName)
        assert len(parsed.sections) == len(SectionName) == 7


# --------------------------------------------------------------------------- #
# Two tables → same section key merge into one section (_merge_table_into_section
# existing-section branch).
# --------------------------------------------------------------------------- #
def test_two_body_tables_merge(
    parser: DocutilsParser, two_body_tables_doc: str
) -> None:
    parsed = parser.parse(two_body_tables_doc, "api-ref/source/v1/create.rst")
    body = _sections(parsed)["body"]
    assert [p.name for p in body.parameters] == ["name", "age"]
    # Field-level metrics are summed across the merged tables, not overwritten.
    assert body.scan_result.fields_total == 2
    assert body.scan_result.fields_recognized == 2
    assert body.scan_result.status is SectionStatus.OK


# --------------------------------------------------------------------------- #
# Example section EXTEND path: an unparseable example arriving second must still
# produce an invalid-JSON issue and degrade the section (review item 14).
# --------------------------------------------------------------------------- #
def test_example_extend_invalid_json_degrades() -> None:
    from tools.scanner.parsers.docutils.doc_parser import _set_example_section

    results: dict = {}
    # First call creates the section from a valid JSON example → OK.
    _set_example_section(
        results,
        SectionName.EXAMPLE_REQUEST,
        [Example(raw='{"a": 1}', parsed={"a": 1})],
    )
    assert results[SectionName.EXAMPLE_REQUEST].scan_result.status is SectionStatus.OK

    # Second call extends the existing section with an unparseable example.
    _set_example_section(
        results,
        SectionName.EXAMPLE_REQUEST,
        [Example(raw="not json", parsed=None)],
    )
    sec = results[SectionName.EXAMPLE_REQUEST]
    assert len(sec.examples) == 2
    assert sec.scan_result.status is SectionStatus.PARTIAL
    assert any(i.code is IssueCode.EXAMPLE_INVALID_JSON for i in sec.scan_result.issues)


# --------------------------------------------------------------------------- #
# api_version falls back to the source file path when the URI carries no
# version segment, and the captured version is lower-cased (review item 15).
# --------------------------------------------------------------------------- #
def test_api_version_from_source_path() -> None:
    extract = DocutilsParser._extract_api_version
    # URI has no version segment; the path does.
    assert extract("/elb/pools", "api-ref/source/v2/create.rst") == "v2"
    # Uppercase V in the path is normalised to lowercase.
    assert extract("/elb/pools", "api-ref/source/V2/create.rst") == "v2"
    # No version anywhere → None.
    assert extract("/elb/pools", "api-ref/source/x.rst") is None
