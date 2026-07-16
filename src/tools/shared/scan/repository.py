"""Repository-level snapshot produced by one scanner session."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    field_validator,
    model_validator,
)
from typing_extensions import Self

from tools import __version__ as _SCANNER_VERSION
from tools.shared.ir import Endpoint, Repository, Service


class RepositoryInterruptionKind(str, enum.Enum):
    """Operational reasons why a repository scan stopped."""

    rate_limit = "rate_limit"
    authentication = "authentication"
    permission_denied = "permission_denied"
    repository_failure = "repository_failure"


@dataclass(frozen=True)
class RepositoryInterruption:
    """Typed repository failure safe to return across application layers."""

    kind: RepositoryInterruptionKind
    repository: str | None
    message: str
    reset_time: int | None = None


class RepositoryScanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: SerializeAsAny[Repository]
    branch: str
    commit_hash: str | None = None
    scanner_version: str = _SCANNER_VERSION

    excluded_documents: list[str] = Field(default_factory=list)

    incomplete_reason: str | None = None
    error: str | None = None
    interruption: RepositoryInterruption | None = None

    @property
    def incomplete(self) -> bool:
        return self.incomplete_reason is not None

    @property
    def failure_message(self) -> str | None:
        if self.error is not None:
            return self.error
        if self.interruption is not None:
            return self.interruption.message
        return None

    @field_validator("repository", mode="before")
    @classmethod
    def restore_service_subclass(cls, repository: object) -> object:
        if isinstance(repository, dict) and repository.get("kind") == "service":
            return Service.model_validate(repository)
        return repository

    @model_validator(mode="after")
    def validate_scan_snapshot(self) -> Self:
        if self.error is not None and self.interruption is not None:
            raise ValueError("error and interruption cannot both be set")

        if not isinstance(self.repository, Service):
            return self

        paths = [document.path for document in self.repository.documents]
        if len(paths) != len(set(paths)):
            raise ValueError("service document paths must be unique")

        for document in self.repository.documents:
            if document.scan_result is None:
                raise ValueError("every service document must have a scan result")
            if isinstance(document, Endpoint) and any(
                section.scan_result is None for section in document.sections
            ):
                raise ValueError("every endpoint section must have a scan result")
        return self
