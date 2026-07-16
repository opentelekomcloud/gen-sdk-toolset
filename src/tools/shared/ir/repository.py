from pydantic import BaseModel


class Repository(BaseModel):
    repo: str
    included: bool = True
