from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ParameterType

#: Schema-v1 spelled an array and its element type as one value. Reading such a
#: payload splits it back apart, so a snapshot stored before this change loads
#: without a migration and means exactly what it meant when it was written.
#: These three are the only composites v1 could express.
_SCHEMA_V1_COMPOSITES: dict[str, tuple[ParameterType, ParameterType]] = {
    "Array of strings": (ParameterType.ARRAY, ParameterType.STRING),
    "Array of integers": (ParameterType.ARRAY, ParameterType.INTEGER),
    "Array of objects": (ParameterType.ARRAY, ParameterType.OBJECT),
}


class Parameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    param_type: ParameterType = ParameterType.UNKNOWN
    #: What an `ARRAY` contains. `None` on an array means the documentation did
    #: not say - which is different from saying it holds objects, and is why
    #: `supports_children` treats the two alike but the IR does not.
    element_type: ParameterType | None = None
    mandatory: bool = False
    description: str = ""
    children: list[Parameter] = Field(default_factory=list)
    #: The documented structure this parameter refers to. Reserved for exactly
    #: that: an array of primitives names no structure and leaves it `None`.
    type_name: str | None = None

    @property
    def supports_children(self) -> bool:
        """Whether a nested table could belong under this parameter.

        Lives here rather than on `ParameterType` because `ARRAY` alone no
        longer answers it - an array of strings holds no structure, an array of
        objects does, and an array whose element type the page never stated
        might. The unknown case is included on purpose: a nested table naming
        this parameter is evidence about what the array holds, and refusing to
        look would throw that evidence away.
        """
        if self.param_type is ParameterType.OBJECT:
            return True
        if self.param_type is ParameterType.ARRAY:
            return self.element_type in (None, ParameterType.OBJECT)
        return False

    @model_validator(mode="before")
    @classmethod
    def split_schema_v1_composites(cls, data: Any) -> Any:
        """Read a schema-v1 `param_type` as the pair it was standing in for."""
        if not isinstance(data, dict):
            return data
        split = _SCHEMA_V1_COMPOSITES.get(data.get("param_type"))
        if split is None:
            return data
        param_type, element_type = split
        return {**data, "param_type": param_type, "element_type": element_type}
