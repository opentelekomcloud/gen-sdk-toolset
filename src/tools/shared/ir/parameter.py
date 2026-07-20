from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import ParameterType


class Parameter(BaseModel):
    name: str
    param_type: ParameterType = ParameterType.UNKNOWN
    mandatory: bool = False
    description: str = ""
    children: list[Parameter] = Field(default_factory=list)
    type_name: str | None = None
