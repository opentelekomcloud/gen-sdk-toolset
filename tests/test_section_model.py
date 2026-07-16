import pytest
from pydantic import ValidationError

from tools.shared.ir import Example, Parameter, Section
from tools.shared.report import Issue, IssueCode, SectionScanResult, SectionStatus


def test_section_data_is_separate_from_scan_diagnostics() -> None:
    section = Section(
        endpoint_path="api-ref/source/create.rst",
        name="path_params",
        parameters=[Parameter(name="project_id")],
    )

    result = SectionScanResult(
        section=section,
        status=SectionStatus.OK,
        fields_total=1,
        fields_recognized=1,
    )

    assert result.section.parameters == [Parameter(name="project_id")]
    assert "parameters" not in SectionScanResult.model_fields
    assert "status" not in Section.model_fields


def test_section_scan_result_rejects_inconsistent_field_metrics() -> None:
    with pytest.raises(ValidationError, match="must add up to fields_total"):
        SectionScanResult(
            section=Section(
                endpoint_path="api-ref/source/create.rst",
                name="body",
            ),
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
            section=Section(
                endpoint_path="api-ref/source/create.rst",
                name="body",
            ),
            status=SectionStatus.PARTIAL,
            **{field_name: -1},
        )


@pytest.mark.parametrize(
    "section",
    [
        Section(
            endpoint_path="api-ref/source/create.rst",
            name="body",
            parameters=[Parameter(name="unexpected")],
        ),
        Section(
            endpoint_path="api-ref/source/create.rst",
            name="example_request",
            examples=[Example(raw="unexpected")],
        ),
    ],
)
def test_missing_section_rejects_extracted_data(section: Section) -> None:
    with pytest.raises(ValidationError, match="cannot contain extracted data"):
        SectionScanResult(section=section, status=SectionStatus.MISSING)


def test_missing_section_rejects_field_metrics() -> None:
    with pytest.raises(ValidationError, match="cannot contain field metrics"):
        SectionScanResult(
            section=Section(
                endpoint_path="api-ref/source/create.rst",
                name="body",
            ),
            status=SectionStatus.MISSING,
            fields_total=1,
            fields_recognized=1,
        )


def test_missing_section_may_explain_absence_with_issue() -> None:
    issue = Issue(code=IssueCode.TABLE_NOT_FOUND)

    result = SectionScanResult(
        section=Section(
            endpoint_path="api-ref/source/create.rst",
            name="body",
        ),
        status=SectionStatus.MISSING,
        issues=[issue],
    )

    assert result.issues == [issue]


def test_example_is_section_data() -> None:
    example = Example(raw='{"name": "example"}', parsed={"name": "example"})
    section = Section(
        endpoint_path="api-ref/source/create.rst",
        name="example_request",
        examples=[example],
    )

    result = SectionScanResult(section=section, status=SectionStatus.OK)

    assert result.section.examples == [example]
    assert "examples" not in SectionScanResult.model_fields


def test_section_rejects_unknown_name() -> None:
    with pytest.raises(ValidationError):
        Section(endpoint_path="api-ref/source/create.rst", name="unknown")
