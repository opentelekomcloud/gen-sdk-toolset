from pydantic import Field, model_validator
from typing_extensions import Self

from .document import Document
from .enums import HttpMethod
from .section import Section


class Endpoint(Document):
    method: HttpMethod
    uri: str
    api_version: str | None = None
    sections: list[Section] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sections(self) -> Self:
        names = [section.name for section in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("endpoint section names must be unique")
        if any(section.endpoint_path != self.path for section in self.sections):
            raise ValueError("section endpoint_path must match endpoint path")
        return self
