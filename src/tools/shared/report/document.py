from pydantic import BaseModel, field_serializer, field_validator, model_validator
from typing_extensions import Self

from tools.shared.ir import Document, Endpoint
from tools.shared.report.issue import Issue


class DocumentScanResult(BaseModel):
    """Document-level outcome of a scan."""

    document: Document
    failure_reason: Issue | None = None

    @field_validator("document", mode="before")
    @classmethod
    def restore_endpoint(cls, value):
        if isinstance(value, dict) and "method" in value and "uri" in value:
            return Endpoint.model_validate(value)
        return value

    @field_serializer("document")
    def serialize_document(self, document: Document) -> dict:
        return document.model_dump(mode="json")

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if isinstance(self.document, Endpoint) and self.failure_reason is not None:
            raise ValueError("a recognized endpoint cannot have a gating failure")
        return self
