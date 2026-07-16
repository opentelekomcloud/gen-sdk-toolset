from typing import Literal

from pydantic import Field, model_validator
from typing_extensions import Self

from .document import Document
from .enums import HttpMethod
from .section import Section, SectionName


class Endpoint(Document):
    kind: Literal["endpoint"] = "endpoint"
    method: HttpMethod
    uri: str
    api_version: str | None = None
    sections: list[Section] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sections(self) -> Self:
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("endpoint section names must be unique")
        if set(names) != set(SectionName):
            raise ValueError("endpoint must contain all seven sections")
        if self.scan_result is not None and self.scan_result.failure_reason is not None:
            raise ValueError("a recognized endpoint cannot have a gating failure")
        return self
