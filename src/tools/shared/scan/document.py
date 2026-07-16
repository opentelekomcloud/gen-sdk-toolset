"""Document-level result produced by one scan."""

from pydantic import BaseModel, ConfigDict

from .issue import Issue


class DocumentScanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_reason: Issue | None = None
