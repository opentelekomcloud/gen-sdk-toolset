from __future__ import annotations

from pydantic import BaseModel, Field

from tools import __version__ as _SCANNER_VERSION
from tools.shared.report.document import DocumentScanResult
from tools.shared.report.section import SectionScanResult
from tools.shared.repository import RepositoryInterruption


class RepoScanResult(BaseModel):
    """Aggregated scan result for one repository."""

    repo: str
    branch: str
    commit_hash: str | None = None
    has_api_ref: bool = False

    scanner_version: str = _SCANNER_VERSION

    documents: list[DocumentScanResult] = Field(default_factory=list)
    section_results: list[SectionScanResult] = Field(default_factory=list)

    non_endpoint_documents: list[str] = Field(default_factory=list)

    excluded_documents: list[str] = Field(default_factory=list)

    documents_by_version: dict[str, list[DocumentScanResult]] = Field(
        default_factory=dict
    )

    incomplete: bool = False
    incomplete_reason: str | None = None
    # todo: do we really need those 2 fields?
    error: str | None = None
    interruption: RepositoryInterruption | None = None
