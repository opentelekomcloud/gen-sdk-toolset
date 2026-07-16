import pytest
from pydantic import ValidationError

from tools.shared.ir import Document, Endpoint, HttpMethod, Section
from tools.shared.report import DocumentScanResult, Issue, IssueCode


def test_endpoint_is_a_document_with_sections() -> None:
    section = Section(
        endpoint_path="api-ref/source/create.rst",
        name="body",
    )
    endpoint = Endpoint(
        path="api-ref/source/create.rst",
        title="Create resource",
        method=HttpMethod.POST,
        uri="/v1/resources",
        api_version="v1",
        sections=[section],
    )

    result = DocumentScanResult(document=endpoint)

    assert isinstance(result.document, Document)
    assert isinstance(result.document, Endpoint)
    assert result.document.sections == [section]
    assert "sections" not in DocumentScanResult.model_fields


def test_document_scan_result_restores_endpoint_subclass() -> None:
    payload = {
        "document": {
            "path": "api-ref/source/create.rst",
            "title": "Create resource",
            "method": "POST",
            "uri": "/v1/resources",
            "api_version": "v1",
            "sections": [],
        },
        "failure_reason": None,
    }

    result = DocumentScanResult.model_validate(payload)

    assert isinstance(result.document, Endpoint)
    assert result.model_dump(mode="json") == payload


def test_endpoint_rejects_section_from_another_document() -> None:
    with pytest.raises(ValidationError, match="must match endpoint path"):
        Endpoint(
            path="api-ref/source/create.rst",
            method=HttpMethod.POST,
            uri="/v1/resources",
            sections=[
                Section(
                    endpoint_path="api-ref/source/delete.rst",
                    name="body",
                )
            ],
        )


def test_recognized_endpoint_cannot_have_gating_failure() -> None:
    endpoint = Endpoint(
        path="api-ref/source/create.rst",
        method=HttpMethod.POST,
        uri="/v1/resources",
    )

    with pytest.raises(ValidationError, match="cannot have a gating failure"):
        DocumentScanResult(
            document=endpoint,
            failure_reason=Issue(code=IssueCode.NO_URI_MATCH),
        )
