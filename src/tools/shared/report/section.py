"""Per-section scan outcome and field-level metrics."""

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from tools.shared.ir import Section
from tools.shared.report.enums import SectionStatus
from tools.shared.report.issue import Issue


class SectionScanResult(BaseModel):
    """Result of attempting to extract one content section of a doc.

    The associated ``Section`` owns extracted parameters and examples. This
    result owns only the scan outcome, issues, and quality metrics.
    """

    section: Section
    status: SectionStatus
    issues: list[Issue] = Field(default_factory=list)

    fields_total: int = Field(default=0, ge=0)
    fields_recognized: int = Field(default=0, ge=0)
    fields_unknown_type: int = Field(default=0, ge=0)
    fields_failed: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_field_metrics(self) -> Self:
        accounted = (
            self.fields_recognized + self.fields_unknown_type + self.fields_failed
        )
        if accounted != self.fields_total:
            raise ValueError(
                "section field metrics must add up to fields_total: "
                f"{accounted} != {self.fields_total}"
            )
        if self.status is SectionStatus.MISSING:
            if self.section.parameters or self.section.examples:
                raise ValueError("a missing section cannot contain extracted data")
            if self.fields_total:
                raise ValueError("a missing section cannot contain field metrics")
        return self
