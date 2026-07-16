from typing import Literal

from pydantic import BaseModel


class Document(BaseModel):
    kind: Literal["document"] = "document"
    path: str
    title: str | None = None
