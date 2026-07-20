import pytest
from pydantic import ValidationError

from tools.shared.ir import (
    Document,
    Endpoint,
    HttpMethod,
    Section,
    SectionName,
    Service,
)
from tools.shared.scan import (
    DocumentScanResult,
    Issue,
    IssueCode,
    SectionScanResult,
    SectionStatus,
)


def _sections() -> list[Section]:
    return [
        Section(
            name=name,
            scan_result=SectionScanResult(status=SectionStatus.MISSING),
        )
        for name in SectionName
    ]


def test_endpoint_is_a_document_with_nested_scan_results() -> None:
    sections = _sections()
    endpoint = Endpoint(
        path="api-ref/source/create.rst",
        title="Create resource",
        method=HttpMethod.POST,
        uri="/v1/resources",
        api_version="v1",
        sections=sections,
        scan_result=DocumentScanResult(),
    )

    assert isinstance(endpoint, Document)
    assert isinstance(endpoint, Endpoint)
    assert endpoint.sections == sections
    assert endpoint.scan_result.failure_reason is None
    assert "document" not in DocumentScanResult.model_fields


def test_service_restores_endpoint_subclass() -> None:
    payload = {
        "kind": "endpoint",
        "path": "api-ref/source/create.rst",
        "title": "Create resource",
        "method": "POST",
        "uri": "/v1/resources",
        "api_version": "v1",
        "sections": [
            {
                "name": name.value,
                "parameters": [],
                "examples": [],
                "scan_result": {
                    "status": "missing",
                    "issues": [],
                    "fields_total": 0,
                    "fields_recognized": 0,
                    "fields_unknown_type": 0,
                    "fields_failed": 0,
                    "unmatched_tables": None,
                },
            }
            for name in SectionName
        ],
        "scan_result": {"failure_reason": None},
    }

    service = Service.model_validate(
        {"kind": "service", "repo": "org/service", "documents": [payload]}
    )
    document = service.documents[0]

    assert isinstance(document, Endpoint)
    assert document.model_dump(mode="json") == payload


def test_service_rejects_unknown_document_kind() -> None:
    with pytest.raises(ValidationError, match="operation"):
        Service.model_validate(
            {
                "kind": "service",
                "repo": "org/service",
                "documents": [
                    {"kind": "operation", "path": "api-ref/source/create.rst"}
                ],
            }
        )


def test_document_kind_rejects_endpoint_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Service.model_validate(
            {
                "kind": "service",
                "repo": "org/service",
                "documents": [
                    {
                        "kind": "document",
                        "path": "api-ref/source/create.rst",
                        "method": "POST",
                        "uri": "/v1/resources",
                        "scan_result": {"failure_reason": None},
                    }
                ],
            }
        )


def test_section_does_not_repeat_endpoint_path() -> None:
    assert "endpoint_path" not in Section.model_fields
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Section.model_validate(
            {
                "endpoint_path": "api-ref/source/create.rst",
                "name": "body",
                "scan_result": {"status": "missing"},
            }
        )


def test_endpoint_requires_all_seven_sections() -> None:
    with pytest.raises(ValidationError, match=f"all {len(SectionName)} sections"):
        Endpoint(
            path="api-ref/source/create.rst",
            method=HttpMethod.POST,
            uri="/v1/resources",
            sections=_sections()[:-1],
            scan_result=DocumentScanResult(),
        )


def test_recognized_endpoint_cannot_have_gating_failure() -> None:
    with pytest.raises(ValidationError, match="cannot have a gating failure"):
        Endpoint(
            path="api-ref/source/create.rst",
            method=HttpMethod.POST,
            uri="/v1/resources",
            sections=_sections(),
            scan_result=DocumentScanResult(
                failure_reason=Issue(code=IssueCode.NO_URI_MATCH)
            ),
        )
