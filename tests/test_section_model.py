import pytest
from pydantic import ValidationError

from tools.shared.ir import Example, Parameter, Section, StatusCode
from tools.shared.scan import (
    Issue,
    IssueCode,
    SectionScanResult,
    SectionStatus,
)


def test_section_data_owns_its_scan_result() -> None:
    section = Section(
        name="path_params",
        parameters=[Parameter(name="project_id")],
        scan_result=SectionScanResult(
            status=SectionStatus.OK,
            fields_total=1,
            fields_recognized=1,
        ),
    )

    assert section.parameters == [Parameter(name="project_id")]
    assert section.scan_result.status is SectionStatus.OK
    assert "section" not in SectionScanResult.model_fields
    assert "scan_result" in Section.model_fields


def test_section_scan_result_rejects_inconsistent_field_metrics() -> None:
    with pytest.raises(ValidationError, match="must add up to fields_total"):
        SectionScanResult(
            status=SectionStatus.PARTIAL,
            fields_total=2,
            fields_recognized=1,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "fields_total",
        "fields_recognized",
        "fields_unknown_type",
        "fields_failed",
    ],
)
def test_section_scan_result_rejects_negative_field_metrics(
    field_name: str,
) -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        SectionScanResult(
            status=SectionStatus.PARTIAL,
            **{field_name: -1},
        )


@pytest.mark.parametrize(
    "section_data",
    [
        {"name": "body", "parameters": [Parameter(name="unexpected")]},
        {"name": "example_request", "examples": [Example(raw="unexpected")]},
    ],
)
def test_missing_section_rejects_extracted_data(section_data: dict) -> None:
    with pytest.raises(ValidationError, match="cannot contain extracted data"):
        Section(
            **section_data,
            scan_result=SectionScanResult(status=SectionStatus.MISSING),
        )


def test_missing_section_rejects_field_metrics() -> None:
    with pytest.raises(ValidationError, match="cannot contain field metrics"):
        SectionScanResult(
            status=SectionStatus.MISSING,
            fields_total=1,
            fields_recognized=1,
        )


def test_missing_section_may_explain_absence_with_issue() -> None:
    issue = Issue(code=IssueCode.UNEXPECTED_COLUMNS)
    section = Section(
        name="body",
        scan_result=SectionScanResult(
            status=SectionStatus.MISSING,
            issues=[issue],
        ),
    )

    assert section.scan_result.issues == [issue]


def test_example_is_section_data() -> None:
    example = Example(raw='{"name": "example"}', parsed={"name": "example"})
    section = Section(
        name="example_request",
        examples=[example],
        scan_result=SectionScanResult(status=SectionStatus.OK),
    )

    assert section.examples == [example]
    assert "examples" not in SectionScanResult.model_fields


def test_section_rejects_unknown_name() -> None:
    with pytest.raises(ValidationError):
        Section(name="unknown")


# --------------------------------------------------------------------------- #
# Status codes
# --------------------------------------------------------------------------- #
def test_a_section_carries_status_codes_apart_from_parameters() -> None:
    """Two lists, not one. A status code has no type and no mandatory flag, so
    folding it into `parameters` would put a row into the field counters that
    answers neither question."""
    section = Section(
        name="status_codes",
        status_codes=[StatusCode(code="200", description="The request succeeded.")],
        scan_result=SectionScanResult(status=SectionStatus.OK),
    )

    assert section.parameters == []
    assert section.examples == []
    assert section.status_codes[0].code == "200"
    assert section.scan_result.fields_total == 0


def test_a_status_code_defaults_to_no_description() -> None:
    """Some tables list a code and nothing else. That is a row, not a failure."""
    assert StatusCode(code="204").description == ""


def test_a_status_code_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        StatusCode(code="200", reason="OK")


def test_a_missing_section_cannot_carry_status_codes() -> None:
    """The same rule the other two lists obey: `missing` is a claim that the
    document had no such section, so it cannot also hold what we read from it."""
    with pytest.raises(ValidationError, match="missing section cannot contain"):
        Section(
            name="status_codes",
            status_codes=[StatusCode(code="200")],
            scan_result=SectionScanResult(status=SectionStatus.MISSING),
        )
