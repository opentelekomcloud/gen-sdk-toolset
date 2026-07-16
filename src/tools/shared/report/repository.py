from __future__ import annotations

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)
from typing_extensions import Self

from tools import __version__ as _SCANNER_VERSION
from tools.shared.ir import Endpoint, RepositoryEntity, Service
from tools.shared.report.document import DocumentScanResult
from tools.shared.report.section import SectionScanResult
from tools.shared.repository import RepositoryInterruption


class RepositoryScanResult(BaseModel):
    repository: RepositoryEntity
    branch: str
    commit_hash: str | None = None
    scanner_version: str = _SCANNER_VERSION

    document_results: list[DocumentScanResult] = Field(default_factory=list)
    section_results: list[SectionScanResult] = Field(default_factory=list)

    non_endpoint_documents: list[str] = Field(default_factory=list)
    excluded_documents: list[str] = Field(default_factory=list)

    incomplete: bool = False
    incomplete_reason: str | None = None
    error: str | None = None
    interruption: RepositoryInterruption | None = None

    @model_validator(mode="after")
    def validate_result_graph(self) -> Self:
        if not isinstance(self.repository, Service):
            if self.document_results or self.section_results:
                raise ValueError("a non-service repository cannot have scan results")
            return self

        documents_by_path = {
            document.path: document for document in self.repository.documents
        }
        result_documents_by_path = {
            result.document.path: result.document for result in self.document_results
        }
        if len(documents_by_path) != len(self.repository.documents):
            raise ValueError("service document paths must be unique")
        if len(result_documents_by_path) != len(self.document_results):
            raise ValueError("documents cannot have multiple scan results")
        if documents_by_path.keys() != result_documents_by_path.keys():
            raise ValueError("every service document must have one document result")
        if any(
            document != result_documents_by_path[path]
            for path, document in documents_by_path.items()
        ):
            raise ValueError(
                "document result must reference the matching service document"
            )

        sections_by_key = {
            (section.endpoint_path, section.name): section
            for document in documents_by_path.values()
            if isinstance(document, Endpoint)
            for section in document.sections
        }
        result_sections_by_key = {
            (result.section.endpoint_path, result.section.name): result.section
            for result in self.section_results
        }
        if len(result_sections_by_key) != len(self.section_results):
            raise ValueError("sections cannot have multiple scan results")
        if sections_by_key.keys() != result_sections_by_key.keys():
            raise ValueError("every endpoint section must have one section result")
        if any(
            section != result_sections_by_key[key]
            for key, section in sections_by_key.items()
        ):
            raise ValueError(
                "section result must reference the matching endpoint section"
            )
        return self
