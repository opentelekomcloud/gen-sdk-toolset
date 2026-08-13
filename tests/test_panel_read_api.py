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


def test_services_list_serves_the_active_snapshot(scanned):
    body = scanned.get("/api/scan/services").json()

    assert body["counts"]["all"] == 1
    (item,) = body["items"]
    assert item["name"] == REPO  # the identifier routes and links use
    assert item["label"] == "ecs"  # what the table prints
    # partial: the plain page's style was not supported, so it stayed unread.
    assert item["scan_status"] == "partial"
    assert item["documents"] == 2  # both documents carry a status
    # Neither: the endpoint left rows unrecognized, the page was never read.
    # The three buckets still add up to the documents with a status.
    assert item["read_in_full"] == 0
    assert item["rows_unrecognized"] == 1
    assert item["unread_documents"] == 1
    assert (
        item["read_in_full"] + item["rows_unrecognized"] + item["unread_documents"]
        == item["documents"]
    )
    # Weighted, not counted: the degraded endpoint is worth half a document and
    # the unsupported page nothing, so half of one document out of two -> 25%.
    assert item["docs_ok"] == 25
    assert item["scanner_version"] == SCANNER_VERSION
    assert item["scanned_at"] is not None
    assert item["docs_changed"] is False  # no head_commit known yet (issue #25)
    # Partial documents are a documentation problem, not something a rescan of
    # the same commit could fix - so no rescan is suggested.
    assert item["rescan_reason"] is None
    assert item["error"] is None
    assert sum(item["overall_breakdown"].values()) == item["documents"]
    # The unsupported page is unread (its style defeated us), so the bar shows
    # it grey - taken out of its colour, never added on top of it.
    assert item["unread_documents"] == 1
    assert item["unread_breakdown"] == {"unsupported": 1}
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
    assert item["docs_ok"] is None  # unknown, not 0%
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


def _exclude(client, repo: str = REPO, reason: str = "retired upstream"):
    return client.post(
        f"/api/scan/services/{repo}/exclude",
        json={"reason": reason, "initiated_by": "operator"},
    )


def test_an_excluded_service_leaves_every_list_but_keeps_its_own_page(scanned):
    """The filter lives in ``_all_services``, so one decision covers the
    registry, the summary counters and the attention rules at once - a service
    hidden from the table but still counted in the header would make the two
    disagree.

    The detail endpoints deliberately keep answering: the UI reads the service
    page to offer the restore, so filtering them too would strand an excluded
    service with no way back through the interface.
    """
    assert _exclude(scanned).status_code == 204

    registry = scanned.get("/api/scan/services").json()
    assert registry["items"] == []
    assert registry["counts"]["all"] == 0

    summary = scanned.get("/api/scan/summary").json()
    assert summary["services_total"] == 0
    assert summary["documents_total"] == 0
    assert summary["last_scanned_at"] is None

    assert scanned.get("/api/scan/attention").json() == []

    detail = scanned.get(f"/api/scan/services/{REPO}")
    assert detail.status_code == 200
    assert detail.json()["name"] == REPO
    assert detail.json()["active_snapshot"]["commit_hash"] == COMMIT
    assert scanned.get(f"/api/scan/services/{REPO}/documents").json()["total"] == 2
    assert scanned.get(f"/api/scan/services/{REPO}/snapshots").status_code == 200
    assert scanned.get(f"/api/scan/services/{REPO}/export").status_code == 200


def test_restoring_a_service_returns_it_to_the_lists_with_its_data(scanned):
    """Exclusion is non-destructive, so a restored service comes back with the
    snapshot it already had rather than as a never-scanned one."""
    assert _exclude(scanned).status_code == 204
    assert scanned.post(f"/api/scan/services/{REPO}/include").status_code == 204

    (item,) = scanned.get("/api/scan/services").json()["items"]
    assert item["name"] == REPO
    assert item["documents"] == 2
    assert item["scan_status"] == "partial"
    assert item["scanner_version"] == SCANNER_VERSION

    summary = scanned.get("/api/scan/summary").json()
    assert summary["services_total"] == 1
    assert summary["documents_total"] == 2


def test_excluding_one_service_leaves_the_others_counted(client, session_factory):
    """Guards the filter against the opposite failure: hiding more than asked.
    The remaining service keeps its own row, its chip count and its rule."""
    _register(session_factory)
    _register(session_factory, "opentelekomcloud-docs/vpc")

    assert _exclude(client).status_code == 204

    registry = client.get("/api/scan/services").json()
    assert [item["name"] for item in registry["items"]] == ["opentelekomcloud-docs/vpc"]
    assert registry["counts"]["all"] == 1
    assert client.get("/api/scan/summary").json()["services_total"] == 1
    rules = {
        rule["code"]: rule["count"] for rule in client.get("/api/scan/attention").json()
    }
    assert rules == {"new": 1}  # only vpc is still counted as never scanned


def test_an_excluded_service_stays_on_the_excluded_list(scanned):
    """The one list that must still show it - otherwise an excluded service
    would be invisible everywhere and impossible to find again."""
    assert _exclude(scanned, reason="retired upstream").status_code == 204

    (row,) = scanned.get("/api/scan/excluded").json()

    assert row["name"] == REPO
    assert row["reason"] == "retired upstream"
    assert row["excluded_by"] == "operator"


# ---------------------------------------------------------------------------
# Service detail, documents, snapshots
# ---------------------------------------------------------------------------


def test_service_detail_adds_snapshot_and_issue_roll_ups(scanned):
    body = scanned.get(f"/api/scan/services/{REPO}").json()

    assert body["name"] == REPO
    assert body["active_snapshot"]["commit_hash"] == COMMIT
    assert body["active_snapshot"]["id"] == body["latest_snapshot"]["id"]
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
    # Pinned to the scanned commit, so the source always matches what was parsed.
    assert body["source_url"] == (
        f"https://github.com/{REPO}/blob/{COMMIT}/api-ref/source/create_server.rst"
    )
    sections = {section["name"]: section for section in body["sections"]}
    assert len(sections) == 7
    body_section = sections["body"]
    assert body_section["status"] == "partial"
    assert body_section["fields_total"] == 2
    assert body_section["fields_recognized"] == 1
    assert body_section["parameters"][0]["name"] == "server"
    assert body_section["parameters"][0]["children"][0]["name"] == "flavor"
    assert body_section["issues"][0]["code"] == "unknown_type_format"
    # Examples travel with their section, verbatim, so they can be compared
    # against what the parser made of them.
    example = sections["example_request"]["examples"][0]
    assert example["raw"] == '{"server": {"flavor": "s3.large"}}'
    assert example["language"] == "json"
    assert example["label"] == "Creating a server"
    assert sections["body"]["examples"] == []


def test_document_of_another_service_is_not_served(scanned, session_factory):
    _register(session_factory, "opentelekomcloud-docs/vpc")
    listing = scanned.get(f"/api/scan/services/{REPO}/documents").json()
    document_id = listing["items"][0]["id"]

    resp = scanned.get(
        f"/api/scan/services/opentelekomcloud-docs/vpc/documents/{document_id}"
    )

    assert resp.status_code == 404


def test_snapshots_list_marks_active_and_latest(scanned, session_factory):
    body = scanned.get(f"/api/scan/services/{REPO}/snapshots").json()

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
        "version_counts": {},
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


def test_documents_can_be_filtered_by_a_section_status(scanned):
    """ "Which documents have a partial body?" - the section rollup shows the
    count, this is how the user reaches the documents behind it."""
    body = scanned.get(
        f"/api/scan/services/{REPO}/documents?section=body&section_status=partial"
    ).json()

    assert [item["path"] for item in body["items"]] == [
        "api-ref/source/create_server.rst"
    ]
    assert body["total"] == 1
    assert body["doc_counts"]["all"] == 1  # counts follow the section filter


def test_section_filter_without_a_status_is_ignored(scanned):
    """One half of the pair alone would quietly mean something else."""
    body = scanned.get(f"/api/scan/services/{REPO}/documents?section=body").json()

    assert body["total"] == 2


def test_section_filter_matching_nothing_returns_an_empty_page(scanned):
    body = scanned.get(
        f"/api/scan/services/{REPO}/documents?section=headers&section_status=failed"
    ).json()

    assert body["items"] == []
    assert body["total"] == 0
    assert body["doc_counts"] == {"all": 0}


def test_messy_documentation_read_in_full_is_scanned_not_partial(
    client, session_factory
):
    """Scan status is about our reading, not about the documentation: an
    endpoint whose tables are all recognized is a complete scan even when the
    documentation earned itself a diagnostic."""
    _register(session_factory)
    endpoint = make_endpoint()
    body = next(s for s in endpoint.sections if s.name.value == "body")
    body.scan_result.fields_recognized = 2  # everything recognized...
    body.scan_result.fields_unknown_type = 0
    # ...while the section still carries the issue that made it partial.
    _run_scan(session_factory, documents=[endpoint])

    (item,) = client.get("/api/scan/services").json()["items"]

    assert item["scan_status"] == "scanned"  # nothing stayed unread
    # The documentation is degraded, not unusable: half a document of one.
    assert item["docs_ok"] == 50


def test_documents_can_be_filtered_by_an_issue_code(scanned):
    """The top-issue chips are counts; this is how a reader reaches the
    documents behind one."""
    body = scanned.get(
        f"/api/scan/services/{REPO}/documents?issue=unknown_type_format"
    ).json()

    assert [item["path"] for item in body["items"]] == [
        "api-ref/source/create_server.rst"
    ]
    assert body["doc_counts"]["all"] == 1


def test_issue_filter_also_matches_a_gating_failure(scanned):
    """`unsupported_doc_style` sits on the document, not on a section - the
    filter has to find it there too."""
    body = scanned.get(
        f"/api/scan/services/{REPO}/documents?issue=unsupported_doc_style"
    ).json()

    assert [item["overall_status"] for item in body["items"]] == ["unsupported"]


def test_documents_can_be_filtered_by_api_version(scanned):
    """The version chips filter the same way the status chips do."""
    body = scanned.get(f"/api/scan/services/{REPO}/documents").json()
    assert body["version_counts"] == {"v1": 1, "unversioned": 1}

    versioned = scanned.get(
        f"/api/scan/services/{REPO}/documents?api_version=v1"
    ).json()
    assert [item["path"] for item in versioned["items"]] == [
        "api-ref/source/create_server.rst"
    ]

    # The chips survive their own filter: counts ignore api_version, so the
    # version a user just clicked is still there to be unclicked.
    assert versioned["version_counts"] == {"v1": 1, "unversioned": 1}

    # A document that names no version is reachable under its own key rather
    # than disappearing from the chips.
    unversioned = scanned.get(
        f"/api/scan/services/{REPO}/documents?api_version=unversioned"
    ).json()
    assert unversioned["total"] == 1


def test_export_returns_the_scanner_contract_as_a_download(scanned):
    """The raw report is a RepositoryScanResult - the same shape the CLI emits,
    not a structure invented for the browser."""
    response = scanned.get(f"/api/scan/services/{REPO}/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert COMMIT[:7] in response.headers["content-disposition"]

    payload = response.json()
    assert payload["commit_hash"] == COMMIT
    assert payload["repository"]["repo"] == REPO
    assert {document["path"] for document in payload["repository"]["documents"]} == {
        "api-ref/source/create_server.rst",
        "api-ref/source/history.rst",
    }
    # It validates as the contract it claims to be.
    from tools.shared.scan import RepositoryScanResult

    assert RepositoryScanResult.model_validate(payload).commit_hash == COMMIT


def test_export_of_an_unscanned_service_is_a_404(client, session_factory):
    _register(session_factory)

    assert client.get(f"/api/scan/services/{REPO}/export").status_code == 404
