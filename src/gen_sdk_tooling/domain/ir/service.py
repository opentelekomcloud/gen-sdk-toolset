from pydantic import BaseModel, Field
from .endpoint import Endpoint


class Service(BaseModel):
    service_name: str
    endpoints: list[Endpoint] = Field(default_factory=list)

    # -- Metadata -----------------------------------------------------------
    # Total RST files found in api-ref/source/
    total_files_found: int = 0
    # Files successfully parsed
    files_parsed: int = 0
    # Files skipped (no URI section, non-API content, etc.)
    files_skipped: int = 0
    # Parsing warnings/issues for review
    parse_warnings: list[str] = Field(default_factory=list)