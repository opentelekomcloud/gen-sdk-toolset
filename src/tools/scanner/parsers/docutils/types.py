from enum import Enum


class SectionKind(str, Enum):
    """High-level role of a top-level section heading inside an RST doc."""

    URI = "uri"
    REQUEST = "request"
    RESPONSE = "response"
    EXAMPLE_REQUEST = "example_request"
    EXAMPLE_RESPONSE = "example_response"
    EXAMPLE_COMBINED = "example_combined"
    STATUS_CODES = "status_codes"
    FUNCTION = "function"
    OTHER = "other"


class TableTarget(str, Enum):
    """Internal routing targets that are not endpoint sections."""

    NESTED_STRUCT = "nested_struct"
    GENERIC_REQUEST = "generic_request"
    INTENTIONALLY_IGNORED = "intentionally_ignored"
    UNMAPPED = "unmapped"


class DocStyle(str, Enum):
    """Layout classification of an RST doc, mapped to report semantics."""

    STYLE_A = "style_a"
    S3_COMPATIBLE = "s3_compatible"
    NOT_ENDPOINT = "not_endpoint"
