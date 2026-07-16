import pytest
from pydantic import ValidationError

from tools import __version__
from tools.shared.ir import Document, Endpoint, HttpMethod, Repository, Service
from tools.shared.report import DocumentScanResult, RepositoryScanResult


def test_service_reuses_repository_identity() -> None:
    endpoint = Endpoint(
        path="api-ref/source/list.rst",
        method=HttpMethod.GET,
        uri="/v1/resources",
    )
    service = Service(repo="org/service", documents=[endpoint])

    assert isinstance(service, Repository)
    assert service.repo == "org/service"
    assert service.endpoints == [endpoint]


def test_repository_scan_result_restores_service_subclass() -> None:
    endpoint_payload = {
        "path": "api-ref/source/list.rst",
        "title": None,
        "method": "GET",
        "uri": "/v1/resources",
        "api_version": "v1",
        "sections": [],
    }
    payload = {
        "repository": {
            "repo": "org/service",
            "included": True,
            "documents": [endpoint_payload],
        },
        "branch": "main",
        "commit_hash": "a" * 40,
        "scanner_version": __version__,
        "document_results": [
            {"document": endpoint_payload, "failure_reason": None}
        ],
        "section_results": [],
        "non_endpoint_documents": [],
        "excluded_documents": [],
        "documents_by_version": {},
        "incomplete": False,
        "incomplete_reason": None,
        "error": None,
        "interruption": None,
    }

    result = RepositoryScanResult.model_validate(payload)

    assert isinstance(result.repository, Service)
    assert isinstance(result.repository.documents[0], Endpoint)
    assert result.model_dump(mode="json") == payload


def test_document_results_reference_service_documents() -> None:
    document = Document(path="api-ref/source/intro.rst")
    result = RepositoryScanResult(
        repository=Service(repo="org/service", documents=[document]),
        branch="main",
        document_results=[DocumentScanResult(document=document)],
    )

    assert result.document_results[0].document == result.repository.documents[0]


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
                DocumentScanResult(
                    document=Document(path="api-ref/source/intro.rst")
                )
            ],
        )
