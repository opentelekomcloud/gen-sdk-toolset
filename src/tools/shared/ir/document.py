from pydantic import BaseModel


class Document(BaseModel):
    path: str
    title: str | None = None
