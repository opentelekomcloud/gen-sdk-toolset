from typing import Literal

from pydantic import BaseModel, ConfigDict


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["document"] = "document"
    path: str
    title: str | None = None
