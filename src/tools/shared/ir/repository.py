from typing import Literal

from pydantic import BaseModel


class Repository(BaseModel):
    kind: Literal["repository"] = "repository"
    repo: str
