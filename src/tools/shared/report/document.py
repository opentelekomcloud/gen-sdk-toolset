from pydantic import BaseModel, model_validator
from typing_extensions import Self

from tools.shared.ir import DocumentEntity, Endpoint
from tools.shared.report.issue import Issue


class DocumentScanResult(BaseModel):
    """Document-level outcome of a scan."""

    document: DocumentEntity
    failure_reason: Issue | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if isinstance(self.document, Endpoint) and self.failure_reason is not None:
            raise ValueError("a recognized endpoint cannot have a gating failure")
        return self
