from pydantic import BaseModel, Field

from .ir import HttpMethod, Service


class ParseError(BaseModel):
    file: str
    line: int | None = None
    message: str


class ParseReport(BaseModel):
    """Legacy aggregate report kept for backward compatibility."""

    service: Service
    total_files: int = 0
    parsed_files: int = 0
    skipped_files: list[str] = Field(default_factory=list)
    errors: list[ParseError] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Scan result models — used by ScannerService for org/repo/document level
# evaluation of documentation parseability.
# --------------------------------------------------------------------------- #
class DocumentScanResult(BaseModel):
    """Result of attempting to parse a single RST document."""

    document: str
    repo: str
    parsed: bool
    method: HttpMethod | None = None
    uri: str | None = None
    title: str | None = None
    api_version: str | None = None
    error: str | None = None


class RepoScanResult(BaseModel):
    """Aggregated scan result for one repository."""

    repo: str
    branch: str
    has_api_ref: bool = False
    total_documents: int = 0
    parsed_count: int = 0
    failed_count: int = 0
    documents: list[DocumentScanResult] = Field(default_factory=list)
    # Successfully parsed documents grouped by API version. Documents whose
    # version could not be determined are keyed under "unversioned".
    # Failed documents are NOT included here — they remain in `documents`.
    documents_by_version: dict[str, list[DocumentScanResult]] = Field(
        default_factory=dict
    )
    error: str | None = None  # Set when the repo itself fails (e.g. tree fetch fails)


class OrgScanResult(BaseModel):
    """Top-level scan result for an organization."""

    org: str
    branch: str
    total_repos: int = 0
    eligible_repos: int = 0
    skipped_repos: list[str] = Field(default_factory=list)
    repos: list[RepoScanResult] = Field(default_factory=list)

    @property
    def total_documents(self) -> int:
        return sum(r.total_documents for r in self.repos)

    @property
    def total_parsed(self) -> int:
        return sum(r.parsed_count for r in self.repos)

    @property
    def total_failed(self) -> int:
        return sum(r.failed_count for r in self.repos)
