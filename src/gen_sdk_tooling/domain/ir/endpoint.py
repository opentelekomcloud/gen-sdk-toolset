from __future__ import annotations
from pydantic import BaseModel, Field
from .enums import HttpMethod, ParameterType


class Parameter(BaseModel):
    name: str
    param_type: ParameterType = ParameterType.UNKNOWN
    mandatory: bool = False
    description: str = ""
    children: list[Parameter] = Field(default_factory=list)


class Endpoint(BaseModel):
    title: str = ""
    description: str = ""
    api_version: str = ""
    # -- URI section --------------------------------------------------------
    method: HttpMethod
    path: str
    # -- Parameters ---------------------------------------------------------
    path_parameters: list[Parameter] = Field(default_factory=list)
    query_parameters: list[Parameter] = Field(default_factory=list)
    # request_headers: list[Parameter]

    request_body: list[Parameter] = Field(default_factory=list)
    response_body: list[Parameter] = Field(default_factory=list)
