from __future__ import annotations

from pydantic import BaseModel, Field

from .example import Example
from .parameter import Parameter


class Section(BaseModel):
    """Extracted data belonging to one endpoint section."""

    endpoint_path: str
    name: str
    parameters: list[Parameter] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
