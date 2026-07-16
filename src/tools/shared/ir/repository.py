from pydantic import BaseModel


class Repository(BaseModel):
    repo: str
