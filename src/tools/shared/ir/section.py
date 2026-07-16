from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .example import Example
from .parameter import Parameter


class SectionName(str, Enum):
    PATH_PARAMS = "path_params"
    QUERY_PARAMS = "query_params"
    HEADERS = "headers"
    BODY = "body"
    RESPONSE = "response"
    EXAMPLE_REQUEST = "example_request"
    EXAMPLE_RESPONSE = "example_response"


class Section(BaseModel):
    """Extracted data belonging to one endpoint section."""

    endpoint_path: str
    name: SectionName
    parameters: list[Parameter] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
