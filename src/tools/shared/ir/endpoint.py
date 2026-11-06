from typing import Literal, Self

from pydantic import Field, model_validator

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
            raise ValueError(f"endpoint must contain all {len(SectionName)} sections")
        if self.scan_result is not None and self.scan_result.failure_reason is not None:
            raise ValueError("a recognized endpoint cannot have a gating failure")
        return self


#: The ``kind`` an endpoint document carries: its discriminator in JSON and in
#: ``DocumentRecord.kind``. Read from the field so the two cannot drift.
ENDPOINT_KIND: str = Endpoint.model_fields["kind"].default
