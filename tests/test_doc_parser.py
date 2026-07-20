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


@pytest.mark.parametrize("uri_line", ["GET", "GET https://api.example.com"])
def test_uri_without_slash_path_raises(parser: DocutilsParser, uri_line: str) -> None:
    content = f"""
URI
---

{uri_line}
"""
    with pytest.raises(ParseFailure) as excinfo:
        parser.parse(content, "empty-uri.rst")
    assert excinfo.value.issue.code is IssueCode.NO_URI_MATCH


def test_uri_placeholder_creates_path_parameter_without_table(
    parser: DocutilsParser,
) -> None:
    content = """
Get Item
========

Function
--------

Returns an item.

URI
---

GET /v1/items/{item_id}
"""

    path_params = _sections(parser.parse(content, "get_item.rst"))["path_params"]

    assert len(path_params.parameters) == 1
    parameter = path_params.parameters[0]
    assert parameter.name == "item_id"
    assert parameter.param_type is ParameterType.STRING
    assert parameter.mandatory is True
    assert parameter.description == ""
    assert path_params.scan_result.status is SectionStatus.OK


def test_uri_table_only_enriches_matching_placeholders(
    parser: DocutilsParser,
) -> None:
    content = """
Get Item
========

Function
--------

Returns an item.

URI
---

GET /v1/items/{item_id}

.. table:: Parameter description

   ======= ========== ============
   Name    Type       Description
   ======= ========== ============
   item_id Integer    Item ID
   payload Dictionary Request data
   ======= ========== ============
"""

    path_params = _sections(parser.parse(content, "get_item.rst"))["path_params"]

    assert [parameter.name for parameter in path_params.parameters] == ["item_id"]
    assert path_params.parameters[0].param_type is ParameterType.STRING
    assert path_params.parameters[0].mandatory is True
    assert path_params.parameters[0].description == "Item ID"
    assert path_params.scan_result.status is SectionStatus.PARTIAL
    assert [issue.code for issue in path_params.scan_result.issues] == [
        IssueCode.PATH_PARAMETER_NOT_IN_URI
    ]
    assert path_params.scan_result.issues[0].location == "payload"


# --------------------------------------------------------------------------- #
# Anti-DDoS — root endpoint from querying_all_api_versions.rst
# --------------------------------------------------------------------------- #
def test_anti_ddos_root_endpoint(
    parser: DocutilsParser, anti_ddos_root_doc: str
) -> None:
    parsed = parser.parse(
        anti_ddos_root_doc,
        "api-ref/source/api/anti-ddos_apis/querying_all_api_versions.rst",
    )

    assert parsed.title == "Querying All API Versions"
    assert parsed.method is HttpMethod.GET
    assert parsed.uri == "/"


def test_anti_ddos_root_endpoint_preserves_examples(
    parser: DocutilsParser, anti_ddos_root_doc: str
) -> None:
    parsed = parser.parse(
        anti_ddos_root_doc,
        "api-ref/source/api/anti-ddos_apis/querying_all_api_versions.rst",
    )
    sections = _sections(parsed)

    assert [example.raw for example in sections["example_request"].examples] == [
        "GET /"
    ]
    request = sections["example_request"]
    assert request.examples[0].language == "text"
    assert request.examples[0].parsed is None
    assert request.scan_result.status is SectionStatus.OK
    assert request.scan_result.issues == []
    assert len(sections["example_response"].examples) == 1
    assert sections["example_response"].examples[0].parsed is not None


def test_anti_ddos_root_endpoint_extracts_top_level_response_table(
    parser: DocutilsParser, anti_ddos_root_doc: str
) -> None:
    parsed = parser.parse(
        anti_ddos_root_doc,
        "api-ref/source/api/anti-ddos_apis/querying_all_api_versions.rst",
    )
    response = _sections(parsed)["response"]

    assert [parameter.name for parameter in response.parameters] == [
        "versions",
        "id",
        "links",
        "min_version",
        "status",
        "updated",
        "version",
    ]
    links = next(
        parameter for parameter in response.parameters if parameter.name == "links"
    )
    versions = next(
        parameter for parameter in response.parameters if parameter.name == "versions"
    )
    assert versions.param_type is ParameterType.ARRAY
    assert versions.children == []
    assert links.param_type is ParameterType.ARRAY_OF_OBJECTS
    assert [child.name for child in links.children] == ["href", "rel"]
    assert response.scan_result.status is SectionStatus.OK
    assert response.scan_result.issues == []


def test_anti_ddos_direct_response_table_is_top_level(
    parser: DocutilsParser, anti_ddos_direct_response_doc: str
) -> None:
    parsed = parser.parse(
        anti_ddos_direct_response_doc,
        "api-ref/source/api/alarm_reminding_apis/updating_alarm_configuration.rst",
    )
    response = _sections(parsed)["response"]

    assert [parameter.name for parameter in response.parameters] == [
        "error_code",
        "error_msg",
        "task_id",
    ]
    assert response.scan_result.status is SectionStatus.OK


def test_caption_based_request_structure_becomes_children(
    parser: DocutilsParser,
) -> None:
    content = """
Create Item
===========

URI
---

POST /v1/items

Request
-------

-  Parameter description

   =========== ========= ===================
   Parameter   Mandatory Type
   =========== ========= ===================
   warn_config Yes       List data structure
   topic_urn   Yes       String
   =========== ========= ===================

.. table:: **Table 2** Description of field **warn_config**

   =========== ========= =======
   Parameter   Mandatory Type
   =========== ========= =======
   antiDDoS    No        Boolean
   bruce_force No        Boolean
   =========== ========= =======
"""

    parsed = parser.parse(content, "create_item.rst")
    body = _sections(parsed)["body"]
    warn_config = next(
        parameter for parameter in body.parameters if parameter.name == "warn_config"
    )

    assert [parameter.name for parameter in body.parameters] == [
        "warn_config",
        "topic_urn",
    ]
    assert [child.name for child in warn_config.children] == [
        "antiDDoS",
        "bruce_force",
    ]
    assert warn_config.param_type is ParameterType.ARRAY_OF_OBJECTS
    assert body.scan_result.fields_total == 2
    assert body.scan_result.status is SectionStatus.OK


def test_label_based_nested_table_without_parent_is_reported(
    parser: DocutilsParser,
) -> None:
    content = """
Get Item
========

URI
---

GET /v1/items

Response
--------

-  Data structure description of **missing_parent**

   ===== ====== ===========
   Name  Type   Description
   ===== ====== ===========
   value String Value
   ===== ====== ===========
"""

    response = _sections(parser.parse(content, "get_item.rst"))["response"]

    assert response.scan_result.status is SectionStatus.FAILED
    assert [issue.code for issue in response.scan_result.issues] == [
        IssueCode.NESTED_PARENT_NOT_FOUND
    ]
    assert response.scan_result.issues[0].location == "missing_parent"


def test_duplicate_label_based_nested_table_is_reported(
    parser: DocutilsParser,
) -> None:
    content = """
Get Item
========

URI
---

GET /v1/items

Response
--------

-  Response parameters

   ===== ============== ===========
   Name  Type           Description
   ===== ============== ===========
   links Data structure Links
   ===== ============== ===========

-  Data structure description of **links**

   ==== ====== ===========
   Name Type   Description
   ==== ====== ===========
   href String Link target
   ==== ====== ===========

-  Data structure description of **links**

   ==== ====== ===========
   Name Type   Description
   ==== ====== ===========
   rel  String Link relation
   ==== ====== ===========
"""

    response = _sections(parser.parse(content, "get_item.rst"))["response"]

    assert [child.name for child in response.parameters[0].children] == ["href"]
    assert response.scan_result.status is SectionStatus.PARTIAL
    assert [issue.code for issue in response.scan_result.issues] == [
        IssueCode.UNMAPPED_TABLE
    ]


def test_anti_ddos_legacy_uri_table_becomes_path_parameters(
    parser: DocutilsParser, anti_ddos_legacy_uri_doc: str
) -> None:
    parsed = parser.parse(
        anti_ddos_legacy_uri_doc,
        "api-ref/source/api/anti-ddos_apis/updating_anti-ddos_defense_policies.rst",
    )
    path_params = _sections(parsed)["path_params"]

    assert parsed.method is HttpMethod.PUT
    assert parsed.uri == "/v1/{project_id}/antiddos/{floating_ip_id}"
    assert [parameter.name for parameter in path_params.parameters] == [
        "project_id",
        "floating_ip_id",
    ]
    assert path_params.scan_result.status is SectionStatus.OK
    assert path_params.scan_result.fields_total == 2


def test_anti_ddos_get_request_parameters_become_query_parameters(
    parser: DocutilsParser, anti_ddos_get_request_doc: str
) -> None:
    parsed = parser.parse(
        anti_ddos_get_request_doc,
        "api-ref/source/api/anti-ddos_apis/querying_anti-ddos_tasks.rst",
    )
    sections = _sections(parsed)

    assert [parameter.name for parameter in sections["path_params"].parameters] == [
        "project_id"
    ]
    assert [parameter.name for parameter in sections["query_params"].parameters] == [
        "task_id"
    ]
    assert sections["query_params"].scan_result.status is SectionStatus.OK
    assert sections["body"].scan_result.status is SectionStatus.MISSING


def test_unmapped_table_degrades_an_extracted_section(parser: DocutilsParser) -> None:
    content = """
Create Item
===========

URI
---

POST /v1/items

Request
-------

.. table:: Request body parameters

   ==== ====== ===========
   Name Type   Description
   ==== ====== ===========
   name String Item name
   ==== ====== ===========

-  Extra structure

   .. table::

      ===== ====== ===========
      Name  Type   Description
      ===== ====== ===========
      extra String Extra value
      ===== ====== ===========
"""

    body = _sections(parser.parse(content, "create_item.rst"))["body"]

    assert [parameter.name for parameter in body.parameters] == ["name"]
    assert body.scan_result.status is SectionStatus.PARTIAL
    assert [issue.code for issue in body.scan_result.issues] == [
        IssueCode.UNMAPPED_TABLE
    ]


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
# Example section EXTEND path: malformed JSON arriving second must still
# produce an issue and degrade the section.
# --------------------------------------------------------------------------- #
def test_example_extend_invalid_json_degrades() -> None:
    from tools.scanner.parsers.docutils.example import add_examples_to_section

    results: dict = {}
    # First call creates the section from a valid JSON example → OK.
    add_examples_to_section(
        results,
        SectionName.EXAMPLE_REQUEST,
        [Example(raw='{"a": 1}', parsed={"a": 1})],
    )
    assert results[SectionName.EXAMPLE_REQUEST].scan_result.status is SectionStatus.OK

    # Second call extends the existing section with an unparseable example.
    add_examples_to_section(
        results,
        SectionName.EXAMPLE_REQUEST,
        [Example(raw='{"a": ...}', parsed=None)],
    )
    sec = results[SectionName.EXAMPLE_REQUEST]
    assert len(sec.examples) == 2
    assert sec.scan_result.status is SectionStatus.PARTIAL
    assert any(i.code is IssueCode.EXAMPLE_INVALID_JSON for i in sec.scan_result.issues)


def test_non_json_example_does_not_degrade() -> None:
    from tools.scanner.parsers.docutils.example import add_examples_to_section

    results: dict = {}
    add_examples_to_section(
        results,
        SectionName.EXAMPLE_REQUEST,
        [Example(raw="GET /v1/items", language="text")],
    )

    section = results[SectionName.EXAMPLE_REQUEST]
    assert section.scan_result.status is SectionStatus.OK
    assert section.scan_result.issues == []


def test_relative_request_uri_is_removed_before_parsing_example_json(
    parser: DocutilsParser,
) -> None:
    content = """Demo
====

URI
---

POST /v1/widgets

Examples
--------

- Example request

  .. code-block:: text

     POST /v1/widgets
     {"widget": {"name": "demo"}}
"""

    parsed = parser.parse(content, "demo.rst")
    request = next(
        section for section in parsed.sections if section.name == "example_request"
    )

    assert request.examples[0].parsed == {"widget": {"name": "demo"}}


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
