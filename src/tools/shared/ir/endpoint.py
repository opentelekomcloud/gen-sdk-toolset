from pydantic import BaseModel, Field

from .enums import HttpMethod
from .parameter import Parameter


class Endpoint(BaseModel):
    title: str = ""
    description: str = ""
    api_version: str = ""
    method: HttpMethod
    path: str
    path_parameters: list[Parameter] = Field(default_factory=list)
    query_parameters: list[Parameter] = Field(default_factory=list)
    request_body: list[Parameter] = Field(default_factory=list)
    response_body: list[Parameter] = Field(default_factory=list)
