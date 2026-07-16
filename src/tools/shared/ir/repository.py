from typing import Literal

from pydantic import BaseModel, ConfigDict


class Repository(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["repository"] = "repository"
    repo: str
