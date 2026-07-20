"""Section-level result produced by one scan."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from .issue import Issue


class SectionStatus(str, Enum):
    """How well one document section was extracted."""

    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"
    MISSING = "missing"


class SectionScanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SectionStatus
    issues: list[Issue] = Field(default_factory=list)
    unmatched_tables: dict[str, list[Any]] | None = None

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
        if self.status is SectionStatus.MISSING and self.fields_total:
            raise ValueError("a missing section cannot contain field metrics")
        return self
