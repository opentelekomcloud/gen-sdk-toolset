"""Narrowing scanner diagnostics down to documentation errors."""

from __future__ import annotations

import pytest

from tools.config import Settings
from tools.scanner.doc_checks import DocCheck, find_doc_errors
from tools.scanner.factory import build_local_doc_provider, build_local_scanner
from tools.shared.ir import (
    Endpoint,
    Example,
    Repository,
    Section,
    SectionName,
    Service,
)
from tools.shared.scan import (
    DocumentScanResult,
    Issue,
    IssueCode,
    RepositoryScanResult,
    SectionScanResult,
    SectionStatus,
)

from .conftest import load_fixture


@pytest.fixture
def scanned(make_git_repo) -> RepositoryScanResult:
    root = make_git_repo(
        {
            "api-ref/source/doc_errors.rst": load_fixture("doc_checks/doc_errors.rst"),
            "api-ref/source/doc_refs.rst": load_fixture("doc_checks/doc_refs.rst"),
        }
    )
    settings = Settings()
    scanner = build_local_scanner(settings, build_local_doc_provider(settings, root))
    return scanner.scan_repository(repo=root.name, branch="main")


def _summary(findings) -> set[tuple[str, DocCheck, str | None, str | None]]:
    return {
        (f.path.rsplit("/", 1)[-1], f.check, f.section, f.location) for f in findings
    }


# --------------------------------------------------------------------------- #
# Checks on scanned documents
# --------------------------------------------------------------------------- #
def test_each_check_names_its_error_in_a_scanned_document(scanned) -> None:
    findings = find_doc_errors(scanned)

    assert _summary(findings) == {
        ("doc_errors.rst", DocCheck.PATH_PARAM_SPELLING, "path_params", "flavors_id"),
        ("doc_errors.rst", DocCheck.TYPE_PROSE, "headers", "row 1"),
        ("doc_errors.rst", DocCheck.TYPE_TABLE_NUMBER, "body", "row 1"),
        ("doc_errors.rst", DocCheck.TYPE_NEAR_PRIMITIVE, "body", "row 2"),
        ("doc_errors.rst", DocCheck.TYPE_REFERENCE_MARKER, "body", "row 3"),
        ("doc_errors.rst", DocCheck.INVALID_JSON, "example_request", "example 1"),
        ("doc_refs.rst", DocCheck.REF_WHOLE_PAGE, "body", "router"),
        (
            "doc_refs.rst",
            DocCheck.EMPTY_CODE_BLOCK,
            "example_response",
            "response block 1",
        ),
    }


def test_table_number_type_is_one_finding_not_two(scanned) -> None:
    """Would catch reporting one Type cell twice: its child table also lacks a
    parent (nested_parent_not_found), but that is the same edit."""
    raw_codes = [
        issue.code
        for doc in scanned.repository.documents
        for section in doc.sections
        for issue in section.scan_result.issues
    ]
    assert IssueCode.NESTED_PARENT_NOT_FOUND in raw_codes

    findings = find_doc_errors(scanned)

    assert [f.check for f in findings].count(DocCheck.TYPE_TABLE_NUMBER) == 1
    assert len(findings) == 8


def test_invalid_json_points_to_the_rst_line(scanned) -> None:
    (finding,) = [
        f for f in find_doc_errors(scanned) if f.check is DocCheck.INVALID_JSON
    ]

    assert finding.line == 65
    assert finding.message == (
        "Example is not valid JSON: Illegal trailing comma before end of object."
    )


def test_messages_quote_the_offending_value(scanned) -> None:
    messages = {f.check: f.message for f in find_doc_errors(scanned)}

    assert "`Table 4`" in messages[DocCheck.TYPE_TABLE_NUMBER]
    assert "Did you mean `integer`?" in messages[DocCheck.TYPE_NEAR_PRIMITIVE]
    assert "`{flavor_id}`" in messages[DocCheck.PATH_PARAM_SPELLING]
    assert "`test_0002`" in messages[DocCheck.REF_WHOLE_PAGE]


def _result(*issues: Issue, section: str = "body", examples=()) -> RepositoryScanResult:
    """One endpoint whose ``section`` carries ``issues``; the rest are empty."""

    def _section(name: SectionName) -> Section:
        if name != section:
            return Section(
                name=name, scan_result=SectionScanResult(status=SectionStatus.MISSING)
            )
        return Section(
            name=name,
            examples=list(examples),
            scan_result=SectionScanResult(
                status=SectionStatus.PARTIAL, issues=list(issues)
            ),
        )

    endpoint = Endpoint(
        path="api-ref/source/x.rst",
        method="GET",
        uri="/v1/{project_id}/things",
        sections=[_section(name) for name in SectionName],
        scan_result=DocumentScanResult(),
    )
    return RepositoryScanResult(
        repository=Service(repo="o/r", documents=[endpoint]),
        branch="main",
        commit_hash="a" * 40,
    )


# --------------------------------------------------------------------------- #
# Diagnostics that are not documentation errors
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "type_cell",
    [
        "Map<String,Array<String>>",
        "File",
        "checkpoint_param",
        "null",
        "Array of BackupResp objects",
        "Dict<enterprise_project>",
        "String",
        "Integer",
    ],
)
def test_type_cells_the_scanner_should_learn_are_not_reported(type_cell) -> None:
    issue = Issue(
        code=IssueCode.UNKNOWN_TYPE_FORMAT, location="row 1", details=type_cell
    )

    assert find_doc_errors(_result(issue)) == []


@pytest.mark.parametrize(
    ("name", "uri"),
    [
        ("image_id", "/v1/{project_id}/scaling_configuration"),
        ("limit", "/v1/{project_id}/things?limit={limit}"),
        ("id", "/v1/{project_id}/things/{uid}"),
    ],
)
def test_parameters_unlike_any_placeholder_are_not_reported(name, uri) -> None:
    issue = Issue(code=IssueCode.PATH_PARAMETER_NOT_IN_URI, location=name, details=uri)

    assert find_doc_errors(_result(issue, section="path_params")) == []


def test_reference_to_a_list_item_is_not_reported() -> None:
    issue = Issue(
        code=IssueCode.NESTED_REF_NOT_A_TABLE,
        location="volumes_links",
        details="evs_04_2005__li1043159617124",
    )

    assert find_doc_errors(_result(issue)) == []


def test_unread_valid_payload_is_not_reported() -> None:
    issue = Issue(
        code=IssueCode.UNMAPPED_BLOCK,
        location="request block 1",
        details='{ "os-getSerialConsole": { "type": "serial" } }',
    )

    assert find_doc_errors(_result(issue, section="example_request")) == []


# --------------------------------------------------------------------------- #
# Invalid JSON: pairing issues with examples
# --------------------------------------------------------------------------- #
def test_invalid_json_pairs_issues_with_broken_examples_in_order() -> None:
    """Would catch pairing by the ``example N`` index, which restarts per batch.

    Two batches were added to the section: [valid, broken] gave "example 2",
    then [broken] gave "example 1" again.
    """
    examples = [
        Example(raw='{"ok": true}', parsed={"ok": True}),
        Example(raw='{"a": 1,}', parsed=None),
        Example(raw='{"b" 2}', parsed=None),
    ]
    issues = [
        Issue(code=IssueCode.EXAMPLE_INVALID_JSON, location="example 2", line=20),
        Issue(code=IssueCode.EXAMPLE_INVALID_JSON, location="example 1", line=30),
    ]

    findings = find_doc_errors(
        _result(*issues, section="example_response", examples=examples)
    )

    assert [(f.line, f.location, f.message) for f in findings] == [
        (
            20,
            "example 2",
            "Example is not valid JSON: Illegal trailing comma before end of object.",
        ),
        (30, "example 1", "Example is not valid JSON: Expecting ':' delimiter."),
    ]


def test_scan_without_documents_has_no_findings() -> None:
    result = RepositoryScanResult(repository=Repository(repo="o/r"), branch="main")

    assert find_doc_errors(result) == []


def test_rows_are_ordered_by_number() -> None:
    issues = [
        Issue(
            code=IssueCode.UNKNOWN_TYPE_FORMAT, location=f"row {n}", details="Table 3"
        )
        for n in (10, 9, 2)
    ]

    findings = find_doc_errors(_result(*issues))

    assert [f.location for f in findings] == ["row 2", "row 9", "row 10"]


@pytest.mark.parametrize("raw", ["null", "true", "42", '"hello"'])
def test_valid_scalar_json_is_not_reported(raw) -> None:
    """Would catch reporting valid JSON: the parser keeps only objects and
    arrays in ``parsed`` and flags a scalar it cannot keep."""
    example = Example(raw=raw, language="json", parsed=None)
    issue = Issue(code=IssueCode.EXAMPLE_INVALID_JSON, location="example 1")

    findings = find_doc_errors(
        _result(issue, section="example_response", examples=[example])
    )

    assert findings == []


def test_scalar_example_does_not_shift_the_pairing() -> None:
    examples = [
        Example(raw="null", language="json", parsed=None),
        Example(raw='{"a": 1,}', language="json", parsed=None),
    ]
    issues = [
        Issue(code=IssueCode.EXAMPLE_INVALID_JSON, location="example 1"),
        Issue(code=IssueCode.EXAMPLE_INVALID_JSON, location="example 2"),
    ]

    findings = find_doc_errors(
        _result(*issues, section="example_response", examples=examples)
    )

    assert [(f.location, f.message) for f in findings] == [
        (
            "example 2",
            "Example is not valid JSON: Illegal trailing comma before end of object.",
        ),
    ]


# --------------------------------------------------------------------------- #
# RST lines
# --------------------------------------------------------------------------- #
def test_every_finding_carries_the_issue_line(scanned) -> None:
    lines = {
        (f.path.rsplit("/", 1)[-1], f.check): f.line for f in find_doc_errors(scanned)
    }

    assert lines == {
        ("doc_errors.rst", DocCheck.PATH_PARAM_SPELLING): 24,
        ("doc_errors.rst", DocCheck.TYPE_PROSE): 35,
        ("doc_errors.rst", DocCheck.TYPE_TABLE_NUMBER): 43,
        ("doc_errors.rst", DocCheck.TYPE_NEAR_PRIMITIVE): 44,
        ("doc_errors.rst", DocCheck.TYPE_REFERENCE_MARKER): 45,
        ("doc_errors.rst", DocCheck.INVALID_JSON): 65,
        ("doc_refs.rst", DocCheck.REF_WHOLE_PAGE): 34,
        ("doc_refs.rst", DocCheck.EMPTY_CODE_BLOCK): 42,
    }
