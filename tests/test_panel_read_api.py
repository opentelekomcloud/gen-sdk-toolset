"""Read endpoints that serve the panel UI (issue #16).

The fixtures ingest a real scan result through ``ingest_service_result``, so
these tests assert on what the panel actually persists rather than on
hand-written rows.

Reuses the PostgreSQL provisioning from tests/test_panel_db.py, so this module
is skipped unless TEST_DATABASE_URL is set or Docker is available.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")
pytest.importorskip("alembic")
pytest.importorskip("httpx")  # required by fastapi.testclient.TestClient

from alembic import command  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from tests.test_panel_db import (  # noqa: E402,F401  (reused DB fixtures)
    _alembic_config,
    admin_url,
    make_endpoint,
    make_plain_document,
    scratch_database,
)
from tools import __version__ as SCANNER_VERSION  # noqa: E402
from tools.panel.api import deps  # noqa: E402
from tools.panel.api.app import create_app  # noqa: E402
from tools.panel.core import ingest as ingest_module  # noqa: E402
from tools.panel.core.db.models import (  # noqa: E402
    ExcludedService,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
)
from tools.panel.core.ingest import ingest_service_result  # noqa: E402
from tools.shared.ir import Service as IrService  # noqa: E402
from tools.shared.scan import RepositoryScanResult  # noqa: E402

REPO = "opentelekomcloud-docs/ecs"
COMMIT = "a" * 40


@pytest.fixture
def engine(scratch_database):  # noqa: F811  (pytest fixture injection)
    url = scratch_database("panel_test_read_api")
    command.upgrade(_alembic_config(url), "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
def client(session_factory, monkeypatch):
    app = create_app()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    monkeypatch.setattr(ingest_module, "SessionLocal", session_factory)
    monkeypatch.setattr(ingest_module, "get_engine", lambda: None)
    return TestClient(app)


def _register(session_factory, repo: str = REPO) -> int:
    with session_factory() as session:
        service = Service(repo=repo, name=repo.split("/")[-1], branch="main")
        session.add(service)
        session.commit()
        return service.id


def _run_scan(session_factory, repo: str = REPO, *, documents=None) -> int:
    """Take a service through a running Job and a successful ingest."""
    with session_factory() as session:
        service_id = session.scalar(select(Service.id).where(Service.repo == repo))
        job = RepositoryScanJob(
            service_id=service_id,
            kind=JobKind.scan,
            status=JobStatus.running,
            initiated_by="tester",
            started_at=datetime.now(tz=UTC),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    result = RepositoryScanResult(
        repository=IrService(
            repo=repo,
            documents=[make_endpoint(), make_plain_document()]
            if documents is None
            else documents,
        ),
        branch="main",
        commit_hash=COMMIT,
    )
    ingest_service_result(job_id=job_id, service_repo=repo, result=result)
    return job_id


@pytest.fixture
def scanned(client, session_factory):
    """One registered, successfully scanned service."""
    _register(session_factory)
    _run_scan(session_factory)
    return client


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_services_list_serves_the_active_generation(scanned):
    body = scanned.get("/api/scan/services").json()

    assert body["counts"]["all"] == 1
    (item,) = body["items"]
    assert item["name"] == REPO
    assert item["scan_status"] == "partial"  # the endpoint scanned partially
    assert item["documents"] == 2  # both documents carry a status
    assert item["struct_ok"] == 50  # completeness 0.5 -> percent
    assert item["scanner_version"] == SCANNER_VERSION
    assert item["scanned_at"] is not None
    assert item["docs_changed"] is False  # no head_commit known yet (issue #25)
    assert item["rescan_reason"] == "partial"
    assert item["error"] is None
    assert sum(item["overall_breakdown"].values()) == item["documents"]
    assert set(item["section_rollup"]) == {
        "path_params",
        "query_params",
        "headers",
        "body",
        "response",
        "example_request",
        "example_response",
    }


def test_never_scanned_service_reports_not_scanned(client, session_factory):
    _register(session_factory)

    (item,) = client.get("/api/scan/services").json()["items"]

    assert item["scan_status"] == "not_scanned"
    assert item["documents"] is None
    assert item["struct_ok"] is None  # unknown, not 0%
    assert item["rescan_reason"] is None


def test_failed_job_surfaces_as_failed_service(client, session_factory):
    _register(session_factory)
    with session_factory() as session:
        service_id = session.scalar(select(Service.id))
        session.add(
            RepositoryScanJob(
                service_id=service_id,
                kind=JobKind.scan,
                status=JobStatus.failed,
                initiated_by="tester",
                started_at=datetime.now(tz=UTC),
                finished_at=datetime.now(tz=UTC),
                error="rate limit exceeded",
            )
        )
        session.commit()

    (item,) = client.get("/api/scan/services").json()["items"]

    assert item["scan_status"] == "failed"
    assert item["error"] == "rate limit exceeded"
    assert item["error_at"] is not None
    assert item["rescan_reason"] == "retry"


def test_services_counts_ignore_the_status_filter(client, session_factory):
    _register(session_factory)
    _register(session_factory, "opentelekomcloud-docs/vpc")
    _run_scan(session_factory)

    body = client.get("/api/scan/services?status=partial").json()

    assert [item["name"] for item in body["items"]] == [REPO]
    assert body["counts"]["all"] == 2  # counts still describe everything matched
    assert body["counts"]["partial"] == 1
    assert body["counts"]["not_scanned"] == 1


def test_services_search_filters_by_repository(client, session_factory):
    _register(session_factory)
    _register(session_factory, "opentelekomcloud-docs/vpc")

    body = client.get("/api/scan/services?q=vpc").json()

    assert [item["name"] for item in body["items"]] == ["opentelekomcloud-docs/vpc"]
    assert body["counts"]["all"] == 1  # search applies to the counts too


def test_summary_counts_services_and_documents(scanned):
    body = scanned.get("/api/scan/summary").json()

    assert body["scanner_version"] == SCANNER_VERSION
    assert body["services_total"] == 1
    assert body["failed_services"] == 0
    assert body["documents_total"] == 2
    assert body["scans_running"] == 0
    assert body["last_scanned_at"] is not None


def test_attention_reports_only_rules_that_fire(client, session_factory):
    _register(session_factory)

    rules = {
        rule["code"]: rule["count"] for rule in client.get("/api/scan/attention").json()
    }

    assert rules == {"new": 1}  # never scanned, never failed


def test_excluded_services_are_listed(client, session_factory):
    service_id = _register(session_factory)
    with session_factory() as session:
        session.add(
            ExcludedService(
                service_id=service_id, reason="deprecated", excluded_by="tester"
            )
        )
        session.commit()

    (row,) = client.get("/api/scan/excluded").json()

    assert row["name"] == REPO
    assert row["reason"] == "deprecated"
    assert row["excluded_by"] == "tester"


# ---------------------------------------------------------------------------
# Service detail, documents, generations
# ---------------------------------------------------------------------------


def test_service_detail_adds_generation_and_issue_roll_ups(scanned):
    body = scanned.get(f"/api/scan/services/{REPO}").json()

    assert body["name"] == REPO
    assert body["active_generation"]["commit_hash"] == COMMIT
    assert body["active_generation"]["id"] == body["latest_generation"]["id"]
    assert body["head_commit"] is None
    assert body["interruption"] is None
    assert body["non_endpoint_documents"] == 0  # both documents have a status
    assert {issue["code"] for issue in body["top_issues"]} == {
        "unknown_type_format",
        "unsupported_doc_style",
    }


def test_unknown_service_returns_404_envelope(client):
    resp = client.get("/api/scan/services/nope/does-not-exist")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_documents_list_is_paged_filtered_and_counted(scanned):
    body = scanned.get(f"/api/scan/services/{REPO}/documents").json()

    assert body["total"] == 2
    assert body["page"] == 1
    assert body["doc_counts"]["all"] == 2
    assert body["doc_counts"]["partial"] == 1
    assert body["doc_counts"]["unsupported"] == 1
    # Worst first: the unsupported page outranks the partial endpoint.
    assert [item["overall_status"] for item in body["items"]] == [
        "partial",
        "unsupported",
    ]
    endpoint_row = body["items"][0]
    assert endpoint_row["method"] == "POST"
    assert endpoint_row["uri"] == "/v1/{project_id}/servers"
    assert endpoint_row["issues"] == [{"code": "unknown_type_format", "count": 1}]


def test_documents_status_filter_keeps_the_full_counts(scanned):
    body = scanned.get(f"/api/scan/services/{REPO}/documents?status=partial").json()

    assert [item["overall_status"] for item in body["items"]] == ["partial"]
    assert body["total"] == 1
    assert body["doc_counts"]["all"] == 2  # chips still show the other bucket


def test_documents_search_matches_path_and_uri(scanned):
    body = scanned.get(f"/api/scan/services/{REPO}/documents?q=create_server").json()

    assert [item["path"] for item in body["items"]] == [
        "api-ref/source/create_server.rst"
    ]
    assert body["doc_counts"]["all"] == 1


def test_document_detail_returns_sections_and_parameters(scanned):
    listing = scanned.get(f"/api/scan/services/{REPO}/documents").json()
    document_id = listing["items"][0]["id"]

    body = scanned.get(f"/api/scan/services/{REPO}/documents/{document_id}").json()

    assert body["api_version"] == "v1"
    assert body["overall_status"] == "partial"
    assert body["failure_reason"] is None
    sections = {section["name"]: section for section in body["sections"]}
    assert len(sections) == 7
    body_section = sections["body"]
    assert body_section["status"] == "partial"
    assert body_section["fields_total"] == 2
    assert body_section["fields_recognized"] == 1
    assert body_section["parameters"][0]["name"] == "server"
    assert body_section["parameters"][0]["children"][0]["name"] == "flavor"
    assert body_section["issues"][0]["code"] == "unknown_type_format"


def test_document_of_another_service_is_not_served(scanned, session_factory):
    _register(session_factory, "opentelekomcloud-docs/vpc")
    listing = scanned.get(f"/api/scan/services/{REPO}/documents").json()
    document_id = listing["items"][0]["id"]

    resp = scanned.get(
        f"/api/scan/services/opentelekomcloud-docs/vpc/documents/{document_id}"
    )

    assert resp.status_code == 404


def test_generations_list_marks_active_and_latest(scanned, session_factory):
    body = scanned.get(f"/api/scan/services/{REPO}/generations").json()

    assert len(body["items"]) == 1
    assert body["active_id"] == body["items"][0]["id"]
    assert body["latest_id"] == body["items"][0]["id"]


def test_documents_of_an_unscanned_service_are_empty_not_404(client, session_factory):
    _register(session_factory)

    body = client.get(f"/api/scan/services/{REPO}/documents").json()

    assert body == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "doc_counts": {"all": 0},
    }


def test_attention_rule_filter_selects_only_matching_services(client, session_factory):
    """Clicking a rule in the attention band filters the registry by that rule,
    not by scan status."""
    _register(session_factory)
    _register(session_factory, "opentelekomcloud-docs/vpc")
    _run_scan(session_factory)  # ecs is scanned; vpc never was

    body = client.get("/api/scan/services?rule=new").json()

    assert [item["name"] for item in body["items"]] == ["opentelekomcloud-docs/vpc"]


def test_attention_rule_failed_selects_the_service_whose_last_job_failed(
    client, session_factory
):
    _register(session_factory)
    _register(session_factory, "opentelekomcloud-docs/vpc")
    with session_factory() as session:
        service_id = session.scalar(select(Service.id).where(Service.repo == REPO))
        session.add(
            RepositoryScanJob(
                service_id=service_id,
                kind=JobKind.scan,
                status=JobStatus.failed,
                initiated_by="tester",
                finished_at=datetime.now(tz=UTC),
                error="boom",
            )
        )
        session.commit()

    body = client.get("/api/scan/services?rule=failed").json()

    assert [item["name"] for item in body["items"]] == [REPO]


def test_services_can_be_sorted_by_name_and_by_documents(client, session_factory):
    _register(session_factory)
    _register(session_factory, "opentelekomcloud-docs/vpc")
    _run_scan(session_factory)  # only ecs has documents

    by_name = client.get("/api/scan/services?sort=name").json()["items"]
    by_docs = client.get("/api/scan/services?sort=docs").json()["items"]

    assert [item["name"] for item in by_name] == [
        REPO,
        "opentelekomcloud-docs/vpc",
    ]
    assert by_docs[0]["name"] == REPO  # most documents first


def test_register_service_command_is_idempotent(session_factory, monkeypatch, capsys):
    """The registry is seeded by hand until discovery (issue #64) exists, so
    re-running the command must not fail or duplicate the service."""
    from tools.panel import cli

    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    monkeypatch.setattr(cli, "get_engine", lambda: None)

    cli._register_command("opentelekomcloud-docs/dns", None, "main")
    cli._register_command("opentelekomcloud-docs/dns", None, "main")

    output = capsys.readouterr().out
    assert "registered opentelekomcloud-docs/dns" in output
    assert "already registered" in output
    with session_factory() as session:
        services = session.scalars(select(Service)).all()
        assert [service.repo for service in services] == ["opentelekomcloud-docs/dns"]
        assert services[0].name == "dns"  # derived from the repo
