from __future__ import annotations

from tools.shared.report.enums import IssueCode
from tools.shared.report.issue import Issue


class GenSdkError(Exception):
    """Base exception for all gen_sdk errors."""


class RepositoryError(GenSdkError):
    """Error accessing a documentation repository."""

    def __init__(
        self, message: str, repo: str | None = None, cause: Exception | None = None
    ):
        super().__init__(message)
        self.repo = repo
        self.cause = cause


class RateLimitError(RepositoryError):
    """GitHub API rate limit exceeded."""

    def __init__(self, reset_time: int | None = None):
        msg = "GitHub API rate limit exceeded"
        if reset_time:
            msg += f". Resets at {reset_time}"
        super().__init__(msg)
        self.reset_time = reset_time


class AuthenticationError(RepositoryError):
    """Authentication failed (invalid or missing token)."""


class NotFoundError(RepositoryError):
    """Repository or file not found."""

    def __init__(self, resource: str, repo: str | None = None):
        super().__init__(f"Not found: {resource}", repo=repo)
        self.resource = resource


class ConfigurationError(GenSdkError):
    """Invalid or missing configuration."""


class ParseFailure(GenSdkError):
    """Raised by the parser when a gating step fails (e.g. no URI in doc).

    Caught at the scanner layer and converted into
    :attr:`DocumentScanResult.failure_reason`.
    """

    def __init__(self, code: IssueCode, details: str | None = None):
        self.issue = Issue(code=code, details=details)
        super().__init__(f"{code.value}" + (f": {details}" if details else ""))
