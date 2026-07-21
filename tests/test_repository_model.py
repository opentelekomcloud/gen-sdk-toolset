import pytest
from pydantic import ValidationError

from tools import __version__
from tools.shared.ir import (
    Document,
    Endpoint,
    HttpMethod,
    Repository,
    Section,
    SectionName,
    Service,
)
from tools.shared.scan import (
    DocumentScanResult,
    RepositoryInterruption,
    RepositoryInterruptionKind,
    RepositoryScanResult,
    SectionScanResult,
    SectionStatus,
)


def _base_sections() -> list[Section]:
    return [Section(name=name) for name in SectionName]


def _sections_with_results() -> list[Section]:
    return [
        Section(
            name=name,
            scan_result=SectionScanResult(status=SectionStatus.MISSING),
        )
        for name in SectionName
    ]


def test_service_reuses_repository_identity() -> None:
    endpoint = Endpoint(
        path="api-ref/source/list.rst",
        method=HttpMethod.GET,
        uri="/v1/resources",
        sections=_base_sections(),
    )
    service = Service(repo="org/service", documents=[endpoint])

    assert isinstance(service, Repository)
    assert service.repo == "org/service"
    assert service.endpoints == [endpoint]


def test_repository_scan_result_restores_nested_service() -> None:
    section_payloads = [
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
    ]
    endpoint_payload = {
        "kind": "endpoint",
        "path": "api-ref/source/list.rst",
        "title": None,
        "method": "GET",
        "uri": "/v1/resources",
        "api_version": "v1",
        "sections": section_payloads,
        "scan_result": {"failure_reason": None},
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
        "excluded_documents": [],
        "incomplete_reason": None,
        "error": None,
        "interruption": None,
    }

    result = RepositoryScanResult.model_validate(payload)

    assert isinstance(result.repository, Service)
    assert isinstance(result.repository.documents[0], Endpoint)
    assert result.model_dump(mode="json") == payload


def test_repository_scan_result_has_one_failure_source() -> None:
    with pytest.raises(
        ValidationError, match="error and interruption cannot both be set"
    ):
        RepositoryScanResult(
            repository=Repository(repo="org/service"),
            branch="main",
            error="eligibility failed",
            interruption=RepositoryInterruption(
                kind=RepositoryInterruptionKind.repository_failure,
                repository="org/service",
                message="eligibility failed",
            ),
        )


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


def test_repository_scan_result_rejects_legacy_flat_results() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RepositoryScanResult.model_validate(
            {
                "repository": {
                    "kind": "service",
                    "repo": "org/service",
                    "documents": [],
                },
                "branch": "main",
                "document_results": [],
                "section_results": [],
            }
        )


def test_scan_result_rejects_duplicate_document_paths() -> None:
    with pytest.raises(ValidationError, match="paths must be unique"):
        RepositoryScanResult(
            repository=Service(
                repo="org/service",
                documents=[
                    Document(
                        path="api-ref/source/intro.rst",
                        scan_result=DocumentScanResult(),
                    ),
                    Document(
                        path="api-ref/source/intro.rst",
                        scan_result=DocumentScanResult(),
                    ),
                ],
            ),
            branch="main",
        )


def test_scan_snapshot_requires_document_result() -> None:
    with pytest.raises(ValidationError, match="scan result"):
        RepositoryScanResult(
            repository=Service(
                repo="org/service",
                documents=[Document(path="api-ref/source/intro.rst")],
            ),
            branch="main",
        )


def test_plain_repository_cannot_contain_documents() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RepositoryScanResult.model_validate(
            {
                "repository": {
                    "kind": "repository",
                    "repo": "org/repository",
                    "documents": [],
                },
                "branch": "main",
            }
        )


def test_endpoint_owns_sections_with_results() -> None:
    endpoint = Endpoint(
        path="api-ref/source/list.rst",
        method=HttpMethod.GET,
        uri="/v1/resources",
        sections=_sections_with_results(),
        scan_result=DocumentScanResult(),
    )
    result = RepositoryScanResult(
        repository=Service(repo="org/service", documents=[endpoint]),
        branch="main",
    )

    assert result.repository.endpoints[0].sections == endpoint.sections
