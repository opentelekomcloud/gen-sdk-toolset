import pytest
from pydantic import ValidationError

from tools import __version__
from tools.shared.ir import (
    Document,
    Endpoint,
    HttpMethod,
    Parameter,
    Repository,
    Section,
    SectionName,
    Service,
)
from tools.shared.report import (
    DocumentScanResult,
    RepositoryScanResult,
    SectionScanResult,
    SectionStatus,
)


def _sections(endpoint_path: str) -> list[Section]:
    return [Section(endpoint_path=endpoint_path, name=name) for name in SectionName]


def test_service_reuses_repository_identity() -> None:
    endpoint = Endpoint(
        path="api-ref/source/list.rst",
        method=HttpMethod.GET,
        uri="/v1/resources",
        sections=_sections("api-ref/source/list.rst"),
    )
    service = Service(repo="org/service", documents=[endpoint])

    assert isinstance(service, Repository)
    assert service.repo == "org/service"
    assert service.endpoints == [endpoint]


def test_repository_scan_result_restores_service_subclass() -> None:
    section_payloads = [
        {
            "endpoint_path": "api-ref/source/list.rst",
            "name": name.value,
            "parameters": [],
            "examples": [],
        }
        for name in SectionName
    ]
    endpoint_payload = {
        "kind": "endpoint",
        "path": "api-ref/source/list.rst",
        "title": None,
        "method": "GET",
        "uri": "/v1/resources",
        "api_version": "v1",
        "sections": section_payloads,
    }
    payload = {
        "repository": {
            "kind": "service",
            "repo": "org/service",
            "documents": [endpoint_payload],
        },
        "branch": "main",
        "commit_hash": "a" * 40,
        "scanner_version": __version__,
        "document_results": [{"document": endpoint_payload, "failure_reason": None}],
        "section_results": [
            {
                "section": section,
                "status": "missing",
                "issues": [],
                "fields_total": 0,
                "fields_recognized": 0,
                "fields_unknown_type": 0,
                "fields_failed": 0,
            }
            for section in section_payloads
        ],
        "non_endpoint_documents": [],
        "excluded_documents": [],
        "incomplete": False,
        "incomplete_reason": None,
        "error": None,
        "interruption": None,
    }

    result = RepositoryScanResult.model_validate(payload)

    assert isinstance(result.repository, Service)
    assert isinstance(result.repository.documents[0], Endpoint)
    assert result.model_dump(mode="json") == payload


def test_repository_scan_result_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError, match="inventory"):
        RepositoryScanResult.model_validate(
            {
                "repository": {"kind": "inventory", "repo": "org/service"},
                "branch": "main",
            }
        )


def test_repository_kind_rejects_service_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RepositoryScanResult.model_validate(
            {
                "repository": {
                    "kind": "repository",
                    "repo": "org/service",
                    "documents": [],
                },
                "branch": "main",
            }
        )


def test_document_results_reference_service_documents() -> None:
    document = Document(path="api-ref/source/intro.rst")
    result = RepositoryScanResult(
        repository=Service(repo="org/service", documents=[document]),
        branch="main",
        document_results=[DocumentScanResult(document=document)],
    )

    assert result.document_results[0].document == result.repository.documents[0]


def test_document_result_rejects_different_entity_with_same_path() -> None:
    path = "api-ref/source/list.rst"
    endpoint = Endpoint(
        path=path,
        method=HttpMethod.GET,
        uri="/v1/resources",
        sections=_sections(path),
    )

    with pytest.raises(ValidationError, match="matching service document"):
        RepositoryScanResult(
            repository=Service(repo="org/service", documents=[endpoint]),
            branch="main",
            document_results=[
                DocumentScanResult(document=Document(path=endpoint.path))
            ],
            section_results=[
                SectionScanResult(section=section, status=SectionStatus.MISSING)
                for section in endpoint.sections
            ],
        )


def test_section_result_rejects_different_entity_with_same_key() -> None:
    path = "api-ref/source/list.rst"
    endpoint = Endpoint(
        path=path,
        method=HttpMethod.GET,
        uri="/v1/resources",
        sections=_sections(path),
    )
    section_results = [
        SectionScanResult(
            section=(
                section.model_copy(
                    update={"parameters": [Parameter(name="unexpected")]}
                )
                if section.name is SectionName.BODY
                else section
            ),
            status=(
                SectionStatus.OK
                if section.name is SectionName.BODY
                else SectionStatus.MISSING
            ),
            fields_total=1 if section.name is SectionName.BODY else 0,
            fields_recognized=1 if section.name is SectionName.BODY else 0,
        )
        for section in endpoint.sections
    ]

    with pytest.raises(ValidationError, match="matching endpoint section"):
        RepositoryScanResult(
            repository=Service(repo="org/service", documents=[endpoint]),
            branch="main",
            document_results=[DocumentScanResult(document=endpoint)],
            section_results=section_results,
        )


def test_service_document_requires_document_result() -> None:
    with pytest.raises(ValidationError, match="must have one document result"):
        RepositoryScanResult(
            repository=Service(
                repo="org/service",
                documents=[Document(path="api-ref/source/intro.rst")],
            ),
            branch="main",
        )


def test_plain_repository_cannot_have_scan_results() -> None:
    with pytest.raises(ValidationError, match="non-service repository"):
        RepositoryScanResult(
            repository=Repository(repo="org/repository"),
            branch="main",
            document_results=[
                DocumentScanResult(document=Document(path="api-ref/source/intro.rst"))
            ],
        )
