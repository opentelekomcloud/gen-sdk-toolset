from typing import Literal

from pydantic import BaseModel, ConfigDict

from tools.shared.scan import DocumentScanResult


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["document"] = "document"
    path: str
    title: str | None = None
    scan_result: DocumentScanResult | None = None
