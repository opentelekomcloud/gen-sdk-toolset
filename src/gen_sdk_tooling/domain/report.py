from pydantic import BaseModel, Field
from .ir import Service

class ParseError(BaseModel):
    file: str
    line: int | None = None
    message: str

class ParseReport(BaseModel):
    service: Service
    total_files: int = 0
    parsed_files: int = 0
    skipped_files: list[str] = Field(default_factory=list)
    errors: list[ParseError] = Field(default_factory=list)
