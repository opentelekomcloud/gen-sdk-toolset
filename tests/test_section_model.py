import pytest
from pydantic import ValidationError

from tools.shared.ir import Example, Parameter, Section
from tools.shared.report import SectionScanResult, SectionStatus


def test_section_data_is_separate_from_scan_diagnostics() -> None:
    section = Section(parameters=[Parameter(name="project_id")])

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
            section=Section(),
            status=SectionStatus.PARTIAL,
            fields_total=2,
            fields_recognized=1,
        )


def test_example_is_section_data() -> None:
    example = Example(raw='{"name": "example"}', parsed={"name": "example"})
    section = Section(examples=[example])

    result = SectionScanResult(section=section, status=SectionStatus.OK)

    assert result.section.examples == [example]
    assert "examples" not in SectionScanResult.model_fields
