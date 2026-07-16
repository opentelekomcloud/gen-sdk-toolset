from __future__ import annotations

from pydantic import (
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)
from typing_extensions import Self

from tools import __version__ as _SCANNER_VERSION
from tools.shared.ir import Endpoint, Repository, Service
from tools.shared.report.document import DocumentScanResult
from tools.shared.report.section import SectionScanResult
from tools.shared.repository import RepositoryInterruption


class RepositoryScanResult(BaseModel):
    repository: Repository
    branch: str
    commit_hash: str | None = None
    scanner_version: str = _SCANNER_VERSION

    document_results: list[DocumentScanResult] = Field(default_factory=list)
    section_results: list[SectionScanResult] = Field(default_factory=list)

    non_endpoint_documents: list[str] = Field(default_factory=list)
    excluded_documents: list[str] = Field(default_factory=list)
    documents_by_version: dict[str, list[DocumentScanResult]] = Field(
        default_factory=dict
    )

    incomplete: bool = False
    incomplete_reason: str | None = None
    error: str | None = None
    interruption: RepositoryInterruption | None = None

    @field_validator("repository", mode="before")
    @classmethod
    def restore_service(cls, repository):
        if isinstance(repository, dict) and "documents" in repository:
            return Service.model_validate(repository)
        return repository

    @field_serializer("repository")
    def serialize_repository(self, repository: Repository) -> dict:
        return repository.model_dump(mode="json")

    @model_validator(mode="after")
    def validate_result_graph(self) -> Self:
        if not isinstance(self.repository, Service):
            if self.document_results or self.section_results:
                raise ValueError("a non-service repository cannot have scan results")
            return self

        document_paths = [document.path for document in self.repository.documents]
        result_paths = [result.document.path for result in self.document_results]
        if len(document_paths) != len(set(document_paths)):
            raise ValueError("service document paths must be unique")
        if len(result_paths) != len(set(result_paths)):
            raise ValueError("documents cannot have multiple scan results")
        if set(document_paths) != set(result_paths):
            raise ValueError("every service document must have one document result")

        section_keys = {
            (section.endpoint_path, section.name)
            for document in self.repository.documents
            if isinstance(document, Endpoint)
            for section in document.sections
        }
        result_keys = [
            (result.section.endpoint_path, result.section.name)
            for result in self.section_results
        ]
        if len(result_keys) != len(set(result_keys)):
            raise ValueError("sections cannot have multiple scan results")
        if section_keys != set(result_keys):
            raise ValueError("every endpoint section must have one section result")
        return self
