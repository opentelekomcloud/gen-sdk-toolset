from __future__ import annotations

import enum

from tools.shared.report.enums import IssueCode
from tools.shared.report.issue import Issue


class GenSdkError(Exception):
    """Base exception for all gen_sdk errors."""


class ProviderErrorKind(str, enum.Enum):
    rate_limit = "rate_limit"
    authentication = "authentication"
    permission_denied = "permission_denied"
    not_found = "not_found"
    connection_error = "connection_error"
    unexpected_response = "unexpected_response"


class ProviderError(GenSdkError):
    """Normalized failure returned by an external data provider."""

    def __init__(
        self,
        message: str,
        *,
        kind: ProviderErrorKind,
        status_code: int | None = None,
        resource: str | None = None,
        reset_time: int | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.resource = resource
        self.reset_time = reset_time
        self.cause = cause


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
