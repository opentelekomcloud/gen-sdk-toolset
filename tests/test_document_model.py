import pytest
from pydantic import ValidationError

from tools.shared.ir import Document, Endpoint, HttpMethod, Section, SectionName
from tools.shared.report import DocumentScanResult, Issue, IssueCode


def _sections(endpoint_path: str) -> list[Section]:
    return [Section(endpoint_path=endpoint_path, name=name) for name in SectionName]


def test_endpoint_is_a_document_with_sections() -> None:
    sections = _sections("api-ref/source/create.rst")
    endpoint = Endpoint(
        path="api-ref/source/create.rst",
        title="Create resource",
        method=HttpMethod.POST,
        uri="/v1/resources",
        api_version="v1",
        sections=sections,
    )

    result = DocumentScanResult(document=endpoint)

    assert isinstance(result.document, Document)
    assert isinstance(result.document, Endpoint)
    assert result.document.sections == sections
    assert {section.name for section in result.document.sections} == set(SectionName)
    assert "sections" not in DocumentScanResult.model_fields


def test_document_scan_result_restores_endpoint_subclass() -> None:
    payload = {
        "document": {
            "kind": "endpoint",
            "path": "api-ref/source/create.rst",
            "title": "Create resource",
            "method": "POST",
            "uri": "/v1/resources",
            "api_version": "v1",
            "sections": [
                {
                    "endpoint_path": "api-ref/source/create.rst",
                    "name": name.value,
                    "parameters": [],
                    "examples": [],
                }
                for name in SectionName
            ],
        },
        "failure_reason": None,
    }

    result = DocumentScanResult.model_validate(payload)

    assert isinstance(result.document, Endpoint)
    assert result.model_dump(mode="json") == payload


def test_document_scan_result_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError, match="operation"):
        DocumentScanResult.model_validate(
            {
                "document": {
                    "kind": "operation",
                    "path": "api-ref/source/create.rst",
                }
            }
        )


def test_endpoint_rejects_section_from_another_document() -> None:
    sections = _sections("api-ref/source/create.rst")
    sections[0] = sections[0].model_copy(
        update={"endpoint_path": "api-ref/source/delete.rst"}
    )
    with pytest.raises(ValidationError, match="must match endpoint path"):
        Endpoint(
            path="api-ref/source/create.rst",
            method=HttpMethod.POST,
            uri="/v1/resources",
            sections=sections,
        )


def test_endpoint_requires_all_seven_sections() -> None:
    with pytest.raises(ValidationError, match="all seven sections"):
        Endpoint(
            path="api-ref/source/create.rst",
            method=HttpMethod.POST,
            uri="/v1/resources",
            sections=_sections("api-ref/source/create.rst")[:-1],
        )


def test_recognized_endpoint_cannot_have_gating_failure() -> None:
    endpoint = Endpoint(
        path="api-ref/source/create.rst",
        method=HttpMethod.POST,
        uri="/v1/resources",
        sections=_sections("api-ref/source/create.rst"),
    )

    with pytest.raises(ValidationError, match="cannot have a gating failure"):
        DocumentScanResult(
            document=endpoint,
            failure_reason=Issue(code=IssueCode.NO_URI_MATCH),
        )
