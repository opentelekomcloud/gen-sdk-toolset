from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from tools.shared.scan import SectionScanResult, SectionStatus

from .example import Example
from .parameter import Parameter


class SectionName(str, Enum):
    PATH_PARAMS = "path_params"
    QUERY_PARAMS = "query_params"
    HEADERS = "headers"
    BODY = "body"
    RESPONSE = "response"
    EXAMPLE_REQUEST = "example_request"
    EXAMPLE_RESPONSE = "example_response"


class Section(BaseModel):
    """Extracted data belonging to one endpoint section."""

    model_config = ConfigDict(extra="forbid")

    name: SectionName
    parameters: list[Parameter] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    scan_result: SectionScanResult | None = None

    @model_validator(mode="after")
    def validate_scan_result(self) -> Self:
        if (
            self.scan_result is not None
            and self.scan_result.status is SectionStatus.MISSING
            and (self.parameters or self.examples)
        ):
            raise ValueError("a missing section cannot contain extracted data")
        return self
