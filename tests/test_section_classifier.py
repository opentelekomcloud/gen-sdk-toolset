"""Tests for section-heading and table-title classification."""

import pytest

from tools.scanner.parsers.docutils.section import (
    SectionKind,
    TableTarget,
    classify_section_title,
    classify_table_title,
    nested_parent_name,
)


# --------------------------------------------------------------------------- #
# Section heading aliases
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "title,expected",
    [
        ("URI", SectionKind.URI),
        ("uri", SectionKind.URI),
        ("Request", SectionKind.REQUEST),
        ("Request Parameters", SectionKind.REQUEST),
        ("Request Message", SectionKind.REQUEST),
        ("Requests", SectionKind.REQUEST),
        ("Response", SectionKind.RESPONSE),
        ("Response Parameters", SectionKind.RESPONSE),
        ("Response Message", SectionKind.RESPONSE),
        ("Response Messages", SectionKind.RESPONSE),
        ("Responses", SectionKind.RESPONSE),
        ("Example Request", SectionKind.EXAMPLE_REQUEST),
        ("Example Requests", SectionKind.EXAMPLE_REQUEST),
        ("Sample Request", SectionKind.EXAMPLE_REQUEST),
        ("Example Response", SectionKind.EXAMPLE_RESPONSE),
        ("Example Responses", SectionKind.EXAMPLE_RESPONSE),
        ("Sample Response", SectionKind.EXAMPLE_RESPONSE),
        ("Example", SectionKind.EXAMPLE_COMBINED),
        ("Examples", SectionKind.EXAMPLE_COMBINED),
        ("Status Code", SectionKind.STATUS_CODES),
        ("Status Codes", SectionKind.STATUS_CODES),
        ("Function", SectionKind.FUNCTION),
        ("Functions", SectionKind.FUNCTION),
    ],
)
def test_known_section_titles(title: str, expected: SectionKind) -> None:
    assert classify_section_title(title) is expected


def test_unknown_title_is_other() -> None:
    assert classify_section_title("Versioning") is SectionKind.OTHER
    assert classify_section_title("WORM") is SectionKind.OTHER


def test_section_case_insensitive() -> None:
    assert classify_section_title("rEqUeSt PaRaMeTeRs") is SectionKind.REQUEST


# --------------------------------------------------------------------------- #
# Table-title classification (context-aware)
# --------------------------------------------------------------------------- #
def test_path_parameters_title() -> None:
    assert (
        classify_table_title("Path Parameters", in_section=SectionKind.URI)
        == "path_params"
    )


def test_uri_parameter() -> None:
    assert (
        classify_table_title("URI parameter", in_section=SectionKind.URI)
        == "path_params"
    )


def test_generic_description_in_uri() -> None:
    assert (
        classify_table_title(
            "Table 1 Parameter description", in_section=SectionKind.URI
        )
        == "path_params"
    )


def test_request_header_table() -> None:
    assert (
        classify_table_title(
            "Parameters in the request header", in_section=SectionKind.REQUEST
        )
        == "headers"
    )


def test_request_body_table() -> None:
    assert (
        classify_table_title("Request body parameters", in_section=SectionKind.REQUEST)
        == "body"
    )


def test_generic_request_table_requires_method_routing() -> None:
    assert (
        classify_table_title(
            "Table 1 Parameter description", in_section=SectionKind.REQUEST
        )
        is TableTarget.GENERIC_REQUEST
    )


def test_response_body_table() -> None:
    assert (
        classify_table_title(
            "Response body parameters", in_section=SectionKind.RESPONSE
        )
        == "response"
    )


def test_data_structure_is_nested() -> None:
    """Tables titled 'Data structure of the X field' are nested struct
    definitions, not body parameter tables."""
    assert (
        classify_table_title(
            "Data structure of the metadata field", in_section=SectionKind.REQUEST
        )
        == "nested_struct"
    )


def test_named_struct_is_nested() -> None:
    """Tables titled with a bare struct name are referenced struct defs."""
    assert (
        classify_table_title("CreateFirewallOption", in_section=SectionKind.REQUEST)
        == "nested_struct"
    )


def test_legacy_nested_label_exposes_parent_name() -> None:
    assert nested_parent_name("Data structure description of warn_config") == (
        "warn_config"
    )
    assert nested_parent_name("Parameter description") is None


def test_status_code_is_intentionally_ignored() -> None:
    """Status-code tables aren't parameter tables — caller should skip them."""
    assert (
        classify_table_title("Status code", in_section=SectionKind.STATUS_CODES)
        is TableTarget.INTENTIONALLY_IGNORED
    )


def test_untitled_table_is_unmapped() -> None:
    assert (
        classify_table_title("", in_section=SectionKind.RESPONSE)
        is TableTarget.UNMAPPED
    )


# --------------------------------------------------------------------------- #
# Query parameters
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "title",
    [
        "Query Parameters",
        "**Table 2** Query Parameters",
        "Query parameter",
        "Parameters in the query",
    ],
)
def test_query_parameters_title(title: str) -> None:
    assert classify_table_title(title, in_section=SectionKind.URI) == "query_params"


def test_query_beats_path_under_uri() -> None:
    """A query table under URI classifies as query_params, never path_params —
    even though the URI-section fallback is path_params."""
    assert (
        classify_table_title("Query Parameters", in_section=SectionKind.URI)
        == "query_params"
    )
    assert (
        classify_table_title("Path Parameters", in_section=SectionKind.URI)
        == "path_params"
    )
