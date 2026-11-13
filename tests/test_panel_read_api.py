"""Read endpoints that serve the panel UI (issue #16).

The fixtures ingest a real scan result through ``ingest_service_result``, so
these tests assert on what the panel actually persists rather than on
hand-written rows.

Reuses the PostgreSQL provisioning from tests/test_panel_db.py, so this module
is skipped unless TEST_DATABASE_URL is set or Docker is available.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")
pytest.importorskip("alembic")
pytest.importorskip("httpx")  # required by fastapi.testclient.TestClient

from alembic import command  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.exc import IntegrityError, OperationalError  # noqa: E402
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
from tools.panel.api.auth import Identity, PanelRole, current_identity  # noqa: E402
from tools.panel.api.routes import generation  # noqa: E402
from tools.panel.api.schemas import (  # noqa: E402
    MoveEndpointRequest,
    RenameResourceRequest,
)
from tools.panel.core import ingest as ingest_module  # noqa: E402
from tools.panel.core import layout as layout_module  # noqa: E402
from tools.panel.core.db.models import (  # noqa: E402
    RESOURCE_NAME_UNIQUE_IN_VERSION,
    TERMINAL_JOB_STATUSES,
    DocumentRecord,
    ExcludedService,
    JobKind,
    JobStatus,
    Layout,
    RepositoryScanJob,
    Resource,
    ResourceEndpoint,
    Service,
    Snapshot,
)
from tools.panel.core.grouping import group_endpoints  # noqa: E402
from tools.panel.core.ingest import ingest_service_result  # noqa: E402
from tools.panel.core.layout import listed_versions  # noqa: E402
from tools.panel.core.spec import ResourceSpec, resource_spec  # noqa: E402
from tools.shared.ir import Document, HttpMethod  # noqa: E402
from tools.shared.ir import Service as IrService  # noqa: E402
from tools.shared.scan import (  # noqa: E402
    DocumentScanResult,
    RepositoryScanResult,
    SectionStatus,
)

REPO = "opentelekomcloud-docs/ecs"
COMMIT = "a" * 40


#: The caller the API tests act as. Deliberately not the name any request body
#: sends, so an assertion on `initiated_by` fails if the body ever wins again.
TEST_WORKER = Identity(
    subject="tester-subject",
    name="test-worker",
    roles=frozenset({PanelRole.worker}),
)


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
    # These suites are about scan behaviour, not about tokens: they run as a
    # worker without minting one. Real token validation, and what a viewer is
    # refused, live in tests/test_panel_auth.py.
    app.dependency_overrides[current_identity] = lambda: TEST_WORKER
    monkeypatch.setattr(ingest_module, "SessionLocal", session_factory)
    monkeypatch.setattr(ingest_module, "get_engine", lambda: None)
    return TestClient(app)


def _register(session_factory, repo: str = REPO) -> int:
    with session_factory() as session:
        service = Service(repo=repo, name=repo.split("/")[-1], branch="main")
        session.add(service)
        session.commit()
        return service.id


def _run_scan(
    session_factory, repo: str = REPO, *, documents=None, commit_hash: str = COMMIT
) -> int:
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
        commit_hash=commit_hash,
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
    assert item["docs_changed"] is False  # this fixture never ran discovery
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
        "status_codes",
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


def test_scanned_at_advances_on_a_rescan_that_changed_nothing(scanned, session_factory):
    """`scanned_at` answers "when did we last read this repository", so an
    unchanged rescan must move it. It reads the latest Snapshot's
    `last_scanned_at`, not its `created_at`: the row is not replaced when
    nothing changed, so a date taken from `created_at` would leave a service
    scanned an hour ago looking untouched for as long as its documentation
    stood still."""
    before = scanned.get("/api/scan/services").json()["items"][0]["scanned_at"]

    _run_scan(session_factory)  # same commit, same documents

    (item,) = scanned.get("/api/scan/services").json()["items"]
    assert item["scanned_at"] > before
    detail = scanned.get(f"/api/scan/services/{REPO}").json()
    assert detail["scanned_at"] == item["scanned_at"]
    # The snapshot itself did not move, which is exactly why the two differ.
    assert detail["active_snapshot"]["created_at"] == before
    with session_factory() as session:
        assert len(session.scalars(select(Snapshot)).all()) == 1


def test_scanned_at_is_absent_until_a_scan_succeeds(client, session_factory):
    _register(session_factory)

    (item,) = client.get("/api/scan/services").json()["items"]

    assert item["scanned_at"] is None


def _set_eligibility(session_factory, repo: str, has_api_ref: bool | None) -> None:
    with session_factory() as session:
        service = session.scalar(select(Service).where(Service.repo == repo))
        service.has_api_ref = has_api_ref
        service.eligibility_checked_at = datetime.now(tz=UTC)
        session.commit()


def test_an_ineligible_repository_is_hidden_from_the_registry_and_counters(
    scanned, session_factory
):
    """``has_api_ref = False`` is discovery's finding that there is nothing to
    scan. Such a row stays in the database - that is the point of storing it -
    but it is not a service the registry, the summary or the attention rules
    should count, or every ineligible repository would sit there forever as a
    service that has never been scanned."""
    _set_eligibility(session_factory, REPO, False)

    registry = scanned.get("/api/scan/services").json()
    assert registry["items"] == []
    assert registry["counts"]["all"] == 0
    assert scanned.get("/api/scan/summary").json()["services_total"] == 0
    assert scanned.get("/api/scan/attention").json() == []


def test_a_repository_never_checked_stays_in_the_registry(client, session_factory):
    """NULL is not False. A service registered by hand has never been through
    discovery, and filtering on ``IS NOT TRUE`` instead would make the whole
    hand-registered registry vanish."""
    _register(session_factory)

    with session_factory() as session:
        assert session.scalars(select(Service)).one().has_api_ref is None

    registry = client.get("/api/scan/services").json()
    assert [item["name"] for item in registry["items"]] == [REPO]
    assert client.get("/api/scan/summary").json()["services_total"] == 1


def test_ineligible_endpoint_serves_the_checked_repositories_alphabetically(
    client, session_factory
):
    _register(session_factory, "opentelekomcloud-docs/website")
    _register(session_factory, "opentelekomcloud-docs/apimon")
    _register(session_factory)  # REPO stays eligible-unknown (NULL)
    _set_eligibility(session_factory, "opentelekomcloud-docs/website", False)
    _set_eligibility(session_factory, "opentelekomcloud-docs/apimon", False)

    rows = client.get("/api/scan/ineligible").json()

    assert [row["repo"] for row in rows] == [
        "opentelekomcloud-docs/apimon",
        "opentelekomcloud-docs/website",
    ]
    assert rows[0]["name"] == "apimon"
    assert rows[0]["branch"] == "main"
    assert rows[0]["checked_at"] is not None


def test_ineligible_endpoint_omits_unchecked_and_eligible_repositories(
    scanned, session_factory
):
    """Only ``IS FALSE`` belongs here. A NULL row is one discovery has not
    reached, and listing it as ineligible would report a check that never ran."""
    _register(session_factory, "opentelekomcloud-docs/vpc")  # NULL
    _set_eligibility(session_factory, REPO, True)

    assert scanned.get("/api/scan/ineligible").json() == []


def _exclude(client, repo: str = REPO, reason: str = "retired upstream"):
    return client.post(
        f"/api/scan/services/{repo}/exclude",
        json={"reason": reason, "initiated_by": "operator"},
    )


def test_an_excluded_service_leaves_every_list_but_keeps_its_own_page(scanned):
    """The filter lives in ``all_services``, so one decision covers the
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
    assert row["excluded_by"] == TEST_WORKER.name  # the token, not the body


# ---------------------------------------------------------------------------
# Service detail, documents, snapshots
# ---------------------------------------------------------------------------


def _set_head(
    session_factory,
    commit: str,
    repo: str = REPO,
    *,
    checked_at: datetime | None = None,
) -> None:
    """What discovery writes when it resolves the branch HEAD (PS2-4)."""
    with session_factory() as session:
        service = session.scalar(select(Service).where(Service.repo == repo))
        service.head_commit = commit
        service.head_checked_at = checked_at or datetime.now(tz=UTC)
        session.commit()


def test_a_head_ahead_of_the_active_snapshot_raises_drift(scanned, session_factory):
    """Populating head_commit is all drift needs: the documentation moved past
    the commit the stored scan was taken at, so the panel says so and suggests
    a rescan. It never launches one - the operator decides."""
    _set_head(session_factory, "f" * 40)

    (item,) = scanned.get("/api/scan/services").json()["items"]
    assert item["docs_changed"] is True
    assert item["rescan_reason"] == "drift"

    rules = {
        rule["code"]: rule["count"]
        for rule in scanned.get("/api/scan/attention").json()
    }
    assert rules["drift"] == 1
    assert scanned.get(f"/api/scan/services/{REPO}").json()["head_commit"] == "f" * 40


def test_drift_clears_once_that_commit_has_been_scanned(scanned, session_factory):
    """Drift is a comparison, not a flag anyone resets: scanning the commit the
    HEAD points at makes the two equal, and the reason disappears on its own."""
    _set_head(session_factory, "f" * 40)
    assert scanned.get("/api/scan/services").json()["items"][0]["docs_changed"] is True

    _run_scan(session_factory, commit_hash="f" * 40)

    (item,) = scanned.get("/api/scan/services").json()["items"]
    assert item["docs_changed"] is False
    assert item["rescan_reason"] is None
    assert "drift" not in {
        rule["code"] for rule in scanned.get("/api/scan/attention").json()
    }


def test_a_rescan_past_the_stored_head_clears_drift(scanned, session_factory):
    """The rescan read a newer HEAD than discovery did: the stored head is the
    older reading, so it no longer says the docs moved past the snapshot."""
    _set_head(session_factory, "f" * 40)
    assert scanned.get("/api/scan/services").json()["items"][0]["docs_changed"] is True

    _run_scan(session_factory, commit_hash="e" * 40)

    (item,) = scanned.get("/api/scan/services").json()["items"]
    assert item["docs_changed"] is False
    assert item["rescan_reason"] is None


def test_a_rescan_that_reuses_the_snapshot_clears_drift(scanned, session_factory):
    """HEAD moved to another commit and back: the rescan reads the active
    snapshot's commit again and reuses it, and that rescan is the latest
    confirmation of the snapshot - not the scan that first produced it."""
    _set_head(session_factory, "f" * 40)
    assert scanned.get("/api/scan/services").json()["items"][0]["docs_changed"] is True

    _run_scan(session_factory, commit_hash=COMMIT)

    with session_factory() as session:
        assert session.scalar(select(func.count(Snapshot.id))) == 1  # reused
    (item,) = scanned.get("/api/scan/services").json()["items"]
    assert item["docs_changed"] is False
    assert item["rescan_reason"] is None


def test_a_head_read_before_the_scan_started_is_not_drift(scanned, session_factory):
    _set_head(session_factory, "f" * 40, checked_at=datetime(2026, 1, 1, tzinfo=UTC))

    (item,) = scanned.get("/api/scan/services").json()["items"]

    assert item["docs_changed"] is False
    assert item["rescan_reason"] is None


def test_a_head_with_no_read_time_is_not_drift(scanned, session_factory):
    with session_factory() as session:
        service = session.scalar(select(Service).where(Service.repo == REPO))
        service.head_commit = "f" * 40
        service.head_checked_at = None
        session.commit()

    (item,) = scanned.get("/api/scan/services").json()["items"]

    assert item["docs_changed"] is False


def test_a_head_matching_the_active_snapshot_is_not_drift(scanned, session_factory):
    _set_head(session_factory, COMMIT)

    (item,) = scanned.get("/api/scan/services").json()["items"]

    assert item["docs_changed"] is False
    assert item["rescan_reason"] is None


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
    assert len(sections) == 8
    body_section = sections["body"]
    assert body_section["status"] == "partial"
    assert body_section["fields_total"] == 2
    assert body_section["fields_recognized"] == 1
    assert body_section["parameters"][0]["name"] == "server"
    assert body_section["parameters"][0]["children"][0]["name"] == "flavor"
    # The array and what it holds travel as two fields, so the table can show
    # `Array<Boolean>` - a type the old composite members could not express.
    server = body_section["parameters"][0]
    assert server["element_type"] is None
    # The structure name travels too, or the table could only ever say
    # `Object` and `Array<Object>` where the page named something.
    assert server["type_name"] == "ServerSpec"
    tags = server["children"][1]
    assert (tags["param_type"], tags["element_type"], tags["type_name"]) == (
        "Array",
        "Object",
        "ServerTag",
    )
    flags = server["children"][2]
    assert (flags["param_type"], flags["element_type"], flags["type_name"]) == (
        "Array",
        "Boolean",
        None,
    )
    assert body_section["issues"][0]["code"] == "unknown_type_format"
    # Examples travel with their section, verbatim, so they can be compared
    # against what the parser made of them.
    example = sections["example_request"]["examples"][0]
    assert example["raw"] == '{"server": {"flavor": "s3.large"}}'
    assert example["language"] == "json"
    assert example["label"] == "Creating a server"
    assert sections["body"]["examples"] == []
    # Status codes ride in their own list, not among the parameters: they have
    # no type and no mandatory flag to put there.
    status = sections["status_codes"]
    assert status["status"] == "ok"
    assert status["parameters"] is None
    assert status["status_codes"] == [
        {"code": "200", "description": "Server created."},
        {"code": "400", "description": "Bad request."},
    ]
    assert sections["body"]["status_codes"] == []


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


def test_snapshots_list_moves_last_scanned_at_on_an_unchanged_rescan(
    scanned, session_factory
):
    """The snapshot picker shows `last_scanned_at`, so this is what makes a
    rescan that changed nothing visible at all. Serving only `created_at`
    would leave the UI identical after a scan the operator just launched, and
    they would have no way to tell it ran."""
    before = scanned.get(f"/api/scan/services/{REPO}/snapshots").json()["items"][0]

    _run_scan(session_factory)  # same commit, same documents

    (item,) = scanned.get(f"/api/scan/services/{REPO}/snapshots").json()["items"]
    assert item["id"] == before["id"]  # still the same snapshot
    assert item["created_at"] == before["created_at"]  # the result did not move
    assert item["last_scanned_at"] > before["last_scanned_at"]  # but it was read


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


# ---------------------------------------------------------------------------
# Snapshot activation - the endpoint is in api/routes/scans.py, but what it
# promises is what the read endpoints answer afterwards.
# ---------------------------------------------------------------------------

#: The commit of the second scan, and the repository HEAD after it.
NEXT_COMMIT = "b" * 40


def _activate(client, snapshot_id: int, repo: str = REPO):
    return client.post(
        f"/api/scan/services/{repo}/snapshots/{snapshot_id}/activate",
        json={"initiated_by": "operator"},
    )


def _queue_job(session_factory, status: JobStatus) -> None:
    """Add one scan Job in ``status``, with the timestamps its CHECK demands."""
    now = datetime.now(tz=UTC)
    with session_factory() as session:
        service_id = session.scalar(select(Service.id).where(Service.repo == REPO))
        session.add(
            RepositoryScanJob(
                service_id=service_id,
                kind=JobKind.scan,
                status=status,
                initiated_by="tester",
                started_at=None if status is JobStatus.queued else now,
                finished_at=now if status in TERMINAL_JOB_STATUSES else None,
                error="boom" if status is JobStatus.failed else None,
            )
        )
        session.commit()


@pytest.fixture
def two_snapshots(scanned, session_factory):
    """One service with two stored Snapshots, and the ids ``(older, latest)``.

    They differ in commit, document count and status breakdown, so an endpoint
    answering from the wrong one fails instead of passing on a lookalike. The
    HEAD stands where discovery would leave it, which is what lets the `drift`
    rule show which Snapshot was served.
    """
    _run_scan(session_factory, documents=[make_endpoint()], commit_hash=NEXT_COMMIT)
    _set_head(session_factory, NEXT_COMMIT)

    body = scanned.get(f"/api/scan/services/{REPO}/snapshots").json()
    latest, older = (item["id"] for item in body["items"])  # newest first
    assert body["active_id"] == latest  # ingest left the newest one active
    return older, latest


def test_activating_an_older_snapshot_moves_active_and_leaves_latest(
    scanned, two_snapshots
):
    older, latest = two_snapshots

    body = _activate(scanned, older).json()

    assert body["active_id"] == older
    assert body["latest_id"] == latest  # the newest result is still the latest
    assert [item["id"] for item in body["items"]] == [latest, older]
    listed = scanned.get(f"/api/scan/services/{REPO}/snapshots").json()
    assert (listed["active_id"], listed["latest_id"]) == (older, latest)


def test_any_stored_snapshot_can_be_activated_including_the_latest_again(
    scanned, two_snapshots
):
    older, latest = two_snapshots
    assert _activate(scanned, older).json()["active_id"] == older

    body = _activate(scanned, latest).json()

    assert body["active_id"] == latest == body["latest_id"]


def test_activating_the_active_snapshot_again_answers_the_same_body(
    scanned, two_snapshots
):
    """Repeating the request is not a conflict: a UI that fires it twice must
    not be told the second one clashed with the first."""
    older, _latest = two_snapshots
    first = _activate(scanned, older)

    second = _activate(scanned, older)

    assert second.status_code == 200
    assert second.json() == first.json()


def test_activation_moves_no_snapshot_and_no_document(
    scanned, two_snapshots, session_factory
):
    """Rewriting a stored Snapshot would make the history a record of what the
    operator looked at rather than of what the scans found."""
    older, _latest = two_snapshots
    with session_factory() as session:
        before = {
            row.id: (row.created_at, row.last_scanned_at, row.commit_hash)
            for row in session.scalars(select(Snapshot))
        }
        documents_before = session.scalars(
            select(DocumentRecord.id).order_by(DocumentRecord.id)
        ).all()

    _activate(scanned, older)

    with session_factory() as session:
        assert {
            row.id: (row.created_at, row.last_scanned_at, row.commit_hash)
            for row in session.scalars(select(Snapshot))
        } == before
        assert (
            session.scalars(select(DocumentRecord.id).order_by(DocumentRecord.id)).all()
            == documents_before
        )


def test_every_read_endpoint_serves_the_newly_active_snapshot(scanned, two_snapshots):
    """An endpoint left reading `latest_snapshot` would report numbers from a
    scan nobody is looking at, and they would look plausible."""
    older, latest = two_snapshots
    assert scanned.get(f"/api/scan/services/{REPO}/documents").json()["total"] == 1

    _activate(scanned, older)

    detail = scanned.get(f"/api/scan/services/{REPO}").json()
    assert detail["active_snapshot"]["id"] == older
    assert detail["active_snapshot"]["commit_hash"] == COMMIT
    assert detail["latest_snapshot"]["id"] == latest
    assert detail["documents"] == 2
    # HEAD is the commit of the latest snapshot, so the pinned one reads as drift.
    assert detail["docs_changed"] is True

    documents = scanned.get(f"/api/scan/services/{REPO}/documents").json()
    assert documents["total"] == 2
    assert documents["doc_counts"] == {"all": 2, "partial": 1, "unsupported": 1}

    assert scanned.get("/api/scan/summary").json()["documents_total"] == 2
    rules = {
        rule["code"]: rule["count"]
        for rule in scanned.get("/api/scan/attention").json()
    }
    assert rules == {"drift": 1}

    export = scanned.get(f"/api/scan/services/{REPO}/export")
    assert COMMIT[:7] in export.headers["content-disposition"]
    assert export.json()["commit_hash"] == COMMIT
    assert len(export.json()["repository"]["documents"]) == 2


def test_a_document_of_the_deactivated_snapshot_is_no_longer_served(
    scanned, two_snapshots
):
    older, _latest = two_snapshots
    listing = scanned.get(f"/api/scan/services/{REPO}/documents").json()
    document_id = listing["items"][0]["id"]  # a document of the latest snapshot

    _activate(scanned, older)

    resp = scanned.get(f"/api/scan/services/{REPO}/documents/{document_id}")
    assert resp.status_code == 404


def test_activating_a_snapshot_of_an_unknown_service_is_404(scanned, two_snapshots):
    older, _latest = two_snapshots

    resp = _activate(scanned, older, repo="opentelekomcloud-docs/nope")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_activating_an_unknown_snapshot_is_404(scanned, two_snapshots):
    _older, latest = two_snapshots

    resp = _activate(scanned, latest + 1000)

    assert resp.status_code == 404


def test_activating_a_snapshot_of_another_service_is_404(scanned, session_factory):
    """Serving it would let one service display another's scan result."""
    _register(session_factory, "opentelekomcloud-docs/vpc")
    _run_scan(session_factory, "opentelekomcloud-docs/vpc")
    foreign = scanned.get(f"/api/scan/services/{REPO}/snapshots").json()["items"][0]

    resp = _activate(scanned, foreign["id"], repo="opentelekomcloud-docs/vpc")

    assert resp.status_code == 404
    vpc = scanned.get("/api/scan/services/opentelekomcloud-docs/vpc").json()
    assert vpc["active_snapshot"]["id"] != foreign["id"]


@pytest.mark.parametrize("status", [JobStatus.queued, JobStatus.running])
def test_activation_is_refused_while_a_scan_is_in_flight(
    scanned, two_snapshots, session_factory, status
):
    """Ingest moves the same pointer, so a switch made now would overwrite the
    scan's result or be overwritten by it, with nothing to show either."""
    older, latest = two_snapshots
    _queue_job(session_factory, status)

    resp = _activate(scanned, older)

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
    # The already active Snapshot is refused too: the guard is about the
    # service's state, not about what the request would change.
    assert _activate(scanned, latest).status_code == 409
    assert scanned.get(f"/api/scan/services/{REPO}/snapshots").json()["active_id"] == (
        latest
    )


@pytest.mark.parametrize("status", sorted(TERMINAL_JOB_STATUSES))
def test_a_finished_scan_never_blocks_activation(
    scanned, two_snapshots, session_factory, status
):
    """A service whose last scan failed is the one most in need of this."""
    older, _latest = two_snapshots
    _queue_job(session_factory, status)

    assert _activate(scanned, older).json()["active_id"] == older


def test_an_excluded_service_can_still_switch_snapshots(scanned, two_snapshots):
    """Exclusion hides a service from the registry; it does not freeze the
    history it owns, and its detail page stays reachable."""
    older, _latest = two_snapshots
    assert _exclude(scanned).status_code == 204

    resp = _activate(scanned, older)

    assert resp.status_code == 200
    assert resp.json()["active_id"] == older


def test_an_unchanged_rescan_leaves_a_pinned_older_snapshot_active(
    scanned, two_snapshots, session_factory
):
    """A rescan matching the latest Snapshot stores nothing and re-points
    nothing: the pinned Snapshot stays active, and only the latest one's
    `last_scanned_at` records that the repository was read."""
    older, latest = two_snapshots
    _activate(scanned, older)
    before = {
        item["id"]: item
        for item in scanned.get(f"/api/scan/services/{REPO}/snapshots").json()["items"]
    }

    _run_scan(session_factory, documents=[make_endpoint()], commit_hash=NEXT_COMMIT)

    body = scanned.get(f"/api/scan/services/{REPO}/snapshots").json()
    assert [item["id"] for item in body["items"]] == [latest, older]  # no duplicate
    assert body["latest_id"] == latest
    assert body["active_id"] == older
    after = {item["id"]: item for item in body["items"]}
    assert after[latest]["last_scanned_at"] > before[latest]["last_scanned_at"]
    assert after[older] == before[older]  # the pinned result was not touched
    with session_factory() as session:
        assert len(session.scalars(select(Snapshot)).all()) == 2


# ---------------------------------------------------------------------------
# Generation list
# ---------------------------------------------------------------------------

GENERATION_LIST = "/api/generation/services"


def _page_without_endpoints() -> Document:
    """A non-endpoint page read cleanly: a snapshot of only this one comes out
    `scanned` and still has no endpoint to generate."""
    return Document(
        path="api-ref/source/overview.rst",
        title="Overview",
        scan_result=DocumentScanResult(),
    )


def _generation_names(client) -> list[str]:
    return [item["name"] for item in client.get(GENERATION_LIST).json()]


def test_generation_list_serves_a_service_whose_active_snapshot_has_endpoints(
    scanned,
):
    assert scanned.get(GENERATION_LIST).json() == [{"name": REPO, "label": "ecs"}]


def test_a_scanned_service_without_endpoints_is_not_on_the_generation_list(
    client, session_factory
):
    """The Scan status does not decide: this service is fully `scanned`, and
    still has nothing to generate."""
    _register(session_factory)
    _run_scan(session_factory, documents=[_page_without_endpoints()])

    (item,) = client.get("/api/scan/services").json()["items"]
    assert item["scan_status"] == "scanned"
    assert client.get(GENERATION_LIST).json() == []


def test_a_never_scanned_service_is_not_on_the_generation_list(client, session_factory):
    _register(session_factory)

    assert client.get(GENERATION_LIST).json() == []


def test_generation_list_reads_the_active_snapshot_not_the_latest(
    scanned, session_factory
):
    """The latest snapshot has no endpoints and the older one has: a list read
    from `latest_snapshot` would answer the other way round once the older one
    is pinned."""
    _run_scan(
        session_factory,
        documents=[_page_without_endpoints()],
        commit_hash=NEXT_COMMIT,
    )
    body = scanned.get(f"/api/scan/services/{REPO}/snapshots").json()
    latest, older = (item["id"] for item in body["items"])
    assert body["active_id"] == latest
    assert scanned.get(GENERATION_LIST).json() == []

    assert _activate(scanned, older).status_code == 200

    assert _generation_names(scanned) == [REPO]


def test_a_running_scan_keeps_a_service_on_the_generation_list(
    scanned, session_factory
):
    _queue_job(session_factory, JobStatus.running)

    assert _generation_names(scanned) == [REPO]


def test_a_first_scan_in_flight_puts_nothing_on_the_generation_list(
    client, session_factory
):
    _register(session_factory)
    _queue_job(session_factory, JobStatus.running)

    assert client.get(GENERATION_LIST).json() == []


def test_a_failed_scan_keeps_a_service_on_the_generation_list(scanned, session_factory):
    _queue_job(session_factory, JobStatus.failed)

    assert _generation_names(scanned) == [REPO]


def test_an_excluded_service_leaves_the_generation_list_until_restored(scanned):
    assert _exclude(scanned).status_code == 204
    assert scanned.get(GENERATION_LIST).json() == []

    assert scanned.post(f"/api/scan/services/{REPO}/include").status_code == 204

    assert _generation_names(scanned) == [REPO]


def test_a_restored_service_without_endpoints_stays_off_the_generation_list(
    client, session_factory
):
    """Restoring brings no special rule with it: the service is checked like
    any other, and a never-scanned one has nothing to show."""
    _register(session_factory)
    assert _exclude(client).status_code == 204
    assert client.post(f"/api/scan/services/{REPO}/include").status_code == 204

    assert client.get(GENERATION_LIST).json() == []


def test_an_ineligible_repository_is_not_on_the_generation_list(
    scanned, session_factory
):
    _set_eligibility(session_factory, REPO, False)

    assert scanned.get(GENERATION_LIST).json() == []


def test_generation_list_search_filters_by_repository(client, session_factory):
    for repo in (REPO, "opentelekomcloud-docs/vpc"):
        _register(session_factory, repo)
        _run_scan(session_factory, repo)

    body = client.get(f"{GENERATION_LIST}?q=VPC").json()

    assert [item["name"] for item in body] == ["opentelekomcloud-docs/vpc"]


def test_generation_list_is_ordered_by_repository(client, session_factory):
    for repo in ("opentelekomcloud-docs/vpc", REPO):
        _register(session_factory, repo)
        _run_scan(session_factory, repo)

    assert _generation_names(client) == [REPO, "opentelekomcloud-docs/vpc"]


# ---------------------------------------------------------------------------
# Generation layout
# ---------------------------------------------------------------------------

LAYOUT = f"/api/generation/services/{REPO}/layout"


def _endpoint(path: str, method: str, uri: str, api_version: str | None):
    return make_endpoint().model_copy(
        update={
            "path": f"api-ref/source/{path}",
            "title": path,
            "method": HttpMethod(method),
            "uri": uri,
            "api_version": api_version,
        }
    )


#: One service's endpoints: two that will form a resource, one left unassigned
#: in v1, one in v2 and one the scanner found no version for.
CREATE_SERVER = _endpoint("create_server.rst", "POST", "/v1/{project_id}/servers", "v1")
LIST_SERVERS = _endpoint("list_servers.rst", "GET", "/v1/{project_id}/servers", "v1")
PROJECT_INFO = _endpoint("project.rst", "GET", "/v1/{project_id}", "v1")
LIST_TAGS = _endpoint("list_tags.rst", "GET", "/v2/{project_id}/tags", "v2")
QUOTAS = _endpoint("quotas.rst", "GET", "/{project_id}/quotas", None)
LAYOUT_ENDPOINTS = [CREATE_SERVER, LIST_SERVERS, PROJECT_INFO, LIST_TAGS, QUOTAS]


def _place(
    session_factory,
    name: str,
    endpoints,
    *,
    api_version: str = "v1",
    confirmed_by: str | None = None,
    repo: str = REPO,
) -> int:
    """Store one resource of ``repo``'s layout holding ``endpoints``."""
    _start_layout(session_factory, repo)
    with session_factory() as session:
        service_id = session.scalar(select(Service.id).where(Service.repo == repo))
        resource = Resource(
            service_id=service_id,
            api_version=api_version,
            name=name,
            confirmed_by=confirmed_by,
            confirmed_at=datetime(2026, 11, 3, tzinfo=UTC) if confirmed_by else None,
        )
        resource.endpoints = [
            ResourceEndpoint(service_id=service_id, path=endpoint.path)
            for endpoint in endpoints
        ]
        session.add(resource)
        session.commit()
        return resource.id


def _start_layout(session_factory, repo: str = REPO) -> None:
    """Record that ``repo``'s preliminary grouping ran, as starting it will."""
    with session_factory() as session:
        service_id = session.scalar(select(Service.id).where(Service.repo == repo))
        if session.get(Layout, service_id) is None:
            session.add(Layout(service_id=service_id, created_by="valeriia"))
            session.commit()


@pytest.fixture
def laid_out(client, session_factory):
    """REPO scanned with LAYOUT_ENDPOINTS and still without a layout."""
    _register(session_factory)
    _run_scan(session_factory, documents=LAYOUT_ENDPOINTS)
    return client


def _paths(items) -> list[str]:
    return [item["path"].removeprefix("api-ref/source/") for item in items]


def test_a_service_whose_grouping_never_ran_has_no_layout(laid_out):
    """Before the grouping runs every endpoint would read as unassigned, though
    nobody has grouped anything yet - so the lists stay empty too."""
    assert laid_out.get(LAYOUT).json() == {
        "has_layout": False,
        "versions": [],
        "no_version": [],
    }


def test_a_grouping_that_made_no_resource_still_shows_both_lists(
    laid_out, session_factory
):
    """Every endpoint may land in "unassigned" or "no version". The layout
    exists all the same, or the user could neither see the endpoints nor start
    placing them."""
    _start_layout(session_factory)

    body = laid_out.get(LAYOUT).json()

    assert body["has_layout"] is True
    v1, v2 = body["versions"]
    assert v1["resources"] == [] and v2["resources"] == []
    assert _paths(v1["unassigned"]) == [
        "project.rst",
        "list_servers.rst",
        "create_server.rst",
    ]
    assert _paths(v2["unassigned"]) == ["list_tags.rst"]
    assert _paths(body["no_version"]) == ["quotas.rst"]


def test_layout_serves_resources_and_derives_both_lists(laid_out, session_factory):
    servers = _place(session_factory, "servers", [LIST_SERVERS, CREATE_SERVER])

    body = laid_out.get(LAYOUT).json()

    assert body["has_layout"] is True
    v1, v2 = body["versions"]
    assert v1["api_version"] == "v1"
    (resource,) = v1["resources"]
    assert resource["id"] == servers
    assert resource["name"] == "servers"
    assert resource["confirmed_by"] is None and resource["confirmed_at"] is None
    # one URI for both: ordered by method then, GET before POST
    assert _paths(resource["endpoints"]) == ["list_servers.rst", "create_server.rst"]
    assert _paths(v1["unassigned"]) == ["project.rst"]
    # a version with unassigned endpoints only is still listed
    assert v2["api_version"] == "v2"
    assert v2["resources"] == []
    assert _paths(v2["unassigned"]) == ["list_tags.rst"]
    assert _paths(body["no_version"]) == ["quotas.rst"]


def test_a_layout_endpoint_is_served_as_the_scan_documents_list_serves_it(
    laid_out, session_factory
):
    _place(session_factory, "servers", [CREATE_SERVER])

    resource = laid_out.get(LAYOUT).json()["versions"][0]["resources"][0]
    (endpoint,) = resource["endpoints"]
    (row,) = laid_out.get(
        f"/api/scan/services/{REPO}/documents?q=create_server"
    ).json()["items"]

    assert endpoint == row
    assert endpoint["path"] == "api-ref/source/create_server.rst"


def test_an_endpoint_from_no_version_stays_in_the_resource_it_was_moved_to(
    laid_out, session_factory
):
    _place(session_factory, "quotas", [QUOTAS], api_version="v2")

    body = laid_out.get(LAYOUT).json()

    assert body["no_version"] == []
    (_, v2) = body["versions"]
    assert _paths(v2["resources"][0]["endpoints"]) == ["quotas.rst"]


def test_a_confirmed_resource_says_who_confirmed_it_and_when(laid_out, session_factory):
    _place(session_factory, "servers", [CREATE_SERVER], confirmed_by="valeriia")

    (resource,) = laid_out.get(LAYOUT).json()["versions"][0]["resources"]

    assert resource["confirmed_by"] == "valeriia"
    assert resource["confirmed_at"].startswith("2026-11-03")


def test_an_endpoint_the_active_snapshot_lacks_is_hidden_and_comes_back_with_it(
    laid_out, session_factory
):
    """The link is kept, not dropped: activating the older snapshot again must
    bring the endpoint back to its resource rather than into "unassigned"."""
    _place(session_factory, "servers", [CREATE_SERVER, LIST_SERVERS])
    _run_scan(
        session_factory,
        documents=[CREATE_SERVER, PROJECT_INFO],
        commit_hash=NEXT_COMMIT,
    )

    (resource,) = laid_out.get(LAYOUT).json()["versions"][0]["resources"]
    assert _paths(resource["endpoints"]) == ["create_server.rst"]

    snapshots = laid_out.get(f"/api/scan/services/{REPO}/snapshots").json()["items"]
    assert _activate(laid_out, snapshots[-1]["id"]).status_code == 200

    (resource,) = laid_out.get(LAYOUT).json()["versions"][0]["resources"]
    assert _paths(resource["endpoints"]) == ["list_servers.rst", "create_server.rst"]


def test_a_resource_whose_endpoints_all_left_keeps_the_layout(
    laid_out, session_factory
):
    _place(session_factory, "tags", [LIST_TAGS], api_version="v2")
    _run_scan(session_factory, documents=[CREATE_SERVER], commit_hash=NEXT_COMMIT)

    body = laid_out.get(LAYOUT).json()

    assert body["has_layout"] is True
    v1, v2 = body["versions"]
    assert v2["resources"][0]["name"] == "tags"
    assert v2["resources"][0]["endpoints"] == []
    assert _paths(v1["unassigned"]) == ["create_server.rst"]


def test_layout_of_a_repository_never_registered_is_not_found(client):
    assert client.get(LAYOUT).status_code == 404


def test_layout_of_an_excluded_service_is_not_found_until_restored(
    laid_out, session_factory
):
    _place(session_factory, "servers", [CREATE_SERVER])
    assert _exclude(laid_out).status_code == 204

    assert laid_out.get(LAYOUT).status_code == 404

    assert laid_out.post(f"/api/scan/services/{REPO}/include").status_code == 204
    assert laid_out.get(LAYOUT).json()["has_layout"] is True


def test_layout_of_a_service_without_endpoints_is_not_found(client, session_factory):
    _register(session_factory)
    _run_scan(session_factory, documents=[_page_without_endpoints()])

    response = client.get(LAYOUT)

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Service not found"}
    }


def test_layout_of_an_ineligible_repository_is_not_found(laid_out, session_factory):
    _set_eligibility(session_factory, REPO, False)

    assert laid_out.get(LAYOUT).status_code == 404


# ---------------------------------------------------------------------------
# Starting the preliminary grouping - the endpoint is in
# api/routes/generation.py, and what it stores is read back through the layout
# read above
# ---------------------------------------------------------------------------


def test_starting_the_grouping_answers_with_the_layout_it_stored(laid_out):
    response = laid_out.post(LAYOUT)

    assert response.status_code == 201
    body = response.json()
    assert body == laid_out.get(LAYOUT).json()
    assert body["has_layout"] is True
    v1, v2 = body["versions"]
    (servers,) = v1["resources"]
    assert servers["name"] == "servers"
    assert servers["confirmed_by"] is None and servers["confirmed_at"] is None
    assert _paths(servers["endpoints"]) == ["list_servers.rst", "create_server.rst"]
    assert _paths(v1["unassigned"]) == ["project.rst"]
    (tags,) = v2["resources"]
    assert tags["name"] == "tags"
    assert _paths(tags["endpoints"]) == ["list_tags.rst"]
    assert v2["unassigned"] == []
    assert _paths(body["no_version"]) == ["quotas.rst"]


def test_only_the_resources_are_stored_and_by_the_caller(laid_out, session_factory):
    """ "Unassigned" and "no version" are derived on read: stored, they would
    stop following the active snapshot."""
    laid_out.post(LAYOUT)

    with session_factory() as session:
        (layout,) = session.scalars(select(Layout)).all()
        stored = sorted(session.scalars(select(ResourceEndpoint.path)))

    assert layout.created_by == TEST_WORKER.name
    assert stored == sorted(
        endpoint.path for endpoint in (CREATE_SERVER, LIST_SERVERS, LIST_TAGS)
    )


def test_a_grouping_without_a_resource_is_still_a_layout(client, session_factory):
    _register(session_factory)
    _run_scan(session_factory, documents=[PROJECT_INFO, QUOTAS])

    body = client.post(LAYOUT).json()

    assert body["has_layout"] is True
    (v1,) = body["versions"]
    assert v1["resources"] == []
    assert _paths(v1["unassigned"]) == ["project.rst"]
    assert _paths(body["no_version"]) == ["quotas.rst"]
    assert client.post(LAYOUT).status_code == 409


def test_a_second_start_is_refused_and_keeps_edits_and_confirmations(
    laid_out, session_factory
):
    _place(session_factory, "renamed", [CREATE_SERVER], confirmed_by="valeriia")
    before = laid_out.get(LAYOUT).json()

    response = laid_out.post(LAYOUT)

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": f"Service {REPO} already has a layout",
        }
    }
    assert laid_out.get(LAYOUT).json() == before


def test_a_layout_without_a_resource_refuses_a_start_too(laid_out, session_factory):
    _start_layout(session_factory)

    assert laid_out.post(LAYOUT).status_code == 409

    with session_factory() as session:
        assert session.scalars(select(Resource)).all() == []


def test_two_concurrent_starts_store_one_layout(laid_out, session_factory):
    """The first start has written its layout but not committed it yet. A
    check before the insert would see no layout and let the second one through;
    the primary key makes it wait for the first, then refuses it."""
    with session_factory() as first:
        service_id = first.scalar(select(Service.id).where(Service.repo == REPO))
        first.add(Layout(service_id=service_id, created_by="first"))
        first.flush()
        response = _start_behind(first, laid_out, session_factory)

    assert response.status_code == 409
    with session_factory() as session:
        assert session.get(Layout, service_id).created_by == "first"
        assert session.scalars(select(Resource)).all() == []


def test_a_start_groups_the_snapshot_an_activation_in_flight_makes_active(
    laid_out, session_factory
):
    """The grouping runs once, so it must not be stored from a snapshot that
    stopped being the active one before the layout was."""
    older = _active_snapshot_id(session_factory)
    _run_scan(session_factory, documents=[CREATE_SERVER], commit_hash=NEXT_COMMIT)
    with session_factory() as first:
        service = first.scalar(
            select(Service).where(Service.repo == REPO).with_for_update()
        )
        service.active_snapshot_id = older
        first.flush()
        response = _start_behind(first, laid_out, session_factory)

    assert response.status_code == 201
    with session_factory() as session:
        stored = sorted(session.scalars(select(Resource.name)))
    assert stored == ["servers", "tags"]


def _active_snapshot_id(session_factory) -> int:
    with session_factory() as session:
        return session.scalar(
            select(Service.active_snapshot_id).where(Service.repo == REPO)
        )


def _start_behind(first, client, session_factory):
    """Start the grouping while ``first`` holds a lock it needs.

    ``first`` commits once the start waits for it - or if it never does, so a
    failed probe is reported instead of leaving the start waiting forever.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        second = pool.submit(client.post, LAYOUT)
        try:
            _wait_for_a_blocked_query(session_factory)
        finally:
            first.commit()
        return second.result(timeout=10)


def _wait_for_a_blocked_query(session_factory, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    with session_factory() as probe:
        while time.monotonic() < deadline:
            blocked = probe.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock'"
                )
            )
            if blocked:
                return
            # pg_stat_activity is read once per transaction
            probe.rollback()
            time.sleep(0.05)
    raise AssertionError("the second start never waited for the first")


def test_a_failed_start_leaves_no_layout_and_can_be_retried(laid_out, monkeypatch):
    def broken(endpoints):
        raise RuntimeError("grouping broke")

    monkeypatch.setattr(layout_module, "group_endpoints", broken)
    # the layout row is already flushed when the grouping fails
    response = TestClient(laid_out.app, raise_server_exceptions=False).post(LAYOUT)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert laid_out.get(LAYOUT).json()["has_layout"] is False

    monkeypatch.setattr(layout_module, "group_endpoints", group_endpoints)
    assert laid_out.post(LAYOUT).status_code == 201


def test_an_empty_api_version_is_no_version_when_started_and_read(
    client, session_factory
):
    empty = _endpoint("empty.rst", "GET", "/v1/{project_id}/servers", "")
    _register(session_factory)
    _run_scan(session_factory, documents=[CREATE_SERVER, empty])

    started = client.post(LAYOUT).json()

    assert started == client.get(LAYOUT).json()
    assert _paths(started["no_version"]) == ["empty.rst"]
    assert [version["api_version"] for version in started["versions"]] == ["v1"]


def test_starting_the_grouping_of_a_repository_never_registered_is_not_found(
    client,
):
    assert client.post(LAYOUT).status_code == 404


def test_starting_the_grouping_of_an_excluded_service_is_not_found(laid_out):
    assert _exclude(laid_out).status_code == 204

    assert laid_out.post(LAYOUT).status_code == 404


def test_starting_the_grouping_of_a_service_without_endpoints_is_not_found(
    client, session_factory
):
    _register(session_factory)
    _run_scan(session_factory, documents=[_page_without_endpoints()])

    assert client.post(LAYOUT).status_code == 404


# ---------------------------------------------------------------------------
# Generation resource spec
# ---------------------------------------------------------------------------


def _spec(resource_id: int, repo: str = REPO, version: str = "v1") -> str:
    return f"/api/generation/services/{repo}/spec/{version}/{resource_id}"


def test_spec_has_operations_and_classes_and_nothing_else(laid_out, session_factory):
    servers = _place(session_factory, "servers", [LIST_SERVERS, CREATE_SERVER])

    response = laid_out.get(_spec(servers))

    assert response.status_code == 200
    assert response.json() == {"operations": [], "classes": []}


def test_spec_is_built_by_a_function_callable_outside_the_route(
    laid_out, session_factory
):
    """The generation job builds its model with the same function (ADR-0114)."""
    servers = _place(session_factory, "servers", [CREATE_SERVER])

    with session_factory() as session:
        service = session.scalars(select(Service).where(Service.repo == REPO)).one()
        spec = resource_spec(session, service, servers)

    assert spec == ResourceSpec(operations=[], classes=[])


def test_spec_of_a_resource_the_layout_lacks_is_not_found(laid_out, session_factory):
    servers = _place(session_factory, "servers", [CREATE_SERVER])

    response = laid_out.get(_spec(servers + 1))

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Resource not found"}
    }


def test_spec_of_another_services_resource_is_not_found(laid_out, session_factory):
    servers = _place(session_factory, "servers", [CREATE_SERVER])
    other = "opentelekomcloud-docs/vpc"
    _register(session_factory, other)
    _run_scan(session_factory, other, documents=[CREATE_SERVER])

    response = laid_out.get(_spec(servers, repo=other))

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Resource not found"


def test_spec_of_a_repository_never_registered_is_not_found(client):
    response = client.get(_spec(1))

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Service not found"


def test_spec_of_an_excluded_service_is_not_found(laid_out, session_factory):
    servers = _place(session_factory, "servers", [CREATE_SERVER])
    assert _exclude(laid_out).status_code == 204

    response = laid_out.get(_spec(servers))

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Service not found"


# ---------------------------------------------------------------------------
# Generation layout edits
# ---------------------------------------------------------------------------

OTHER_REPO = "opentelekomcloud-docs/vpc"
#: An endpoint only OTHER_REPO has: REPO's layout must not take it.
VPC_ONLY = _endpoint("list_vpcs.rst", "GET", "/v1/{project_id}/vpcs", "v1")


def _add(client, name: str, api_version: str = "v1", repo: str = REPO):
    return client.post(
        f"/api/generation/services/{repo}/layout/resources",
        json={"api_version": api_version, "name": name},
    )


def _rename(client, resource_id: int, name: str, repo: str = REPO):
    return client.post(
        f"/api/generation/services/{repo}/layout/resources/{resource_id}/rename",
        json={"name": name},
    )


def _move(client, path: str, resource_id: int, repo: str = REPO):
    return client.post(
        f"/api/generation/services/{repo}/layout/endpoints/move",
        json={"path": path, "resource_id": resource_id},
    )


def _version(body, api_version: str) -> dict:
    [version] = [v for v in body["versions"] if v["api_version"] == api_version]
    return version


def _named(body, api_version: str, name: str) -> dict:
    [resource] = [
        r for r in _version(body, api_version)["resources"] if r["name"] == name
    ]
    return resource


def _refused(client, response, status: int, message: str) -> None:
    """The edit was refused through the error envelope, naming why."""
    assert response.status_code == status
    error = response.json()["error"]
    assert (
        error["code"]
        == {404: "not_found", 409: "conflict", 422: "validation_error"}[status]
    )
    assert message in error["message"]


@pytest.fixture
def other_service(laid_out, session_factory):
    """A second service on the Generation list, with a layout of its own."""
    _register(session_factory, OTHER_REPO)
    _run_scan(session_factory, OTHER_REPO, documents=[VPC_ONLY])
    return _place(session_factory, "vpcs", [VPC_ONLY], repo=OTHER_REPO)


# --- rename ----------------------------------------------------------------


def test_a_renamed_resource_keeps_its_id_and_its_endpoints(laid_out, session_factory):
    servers = _place(session_factory, "servers", [LIST_SERVERS, CREATE_SERVER])

    response = _rename(laid_out, servers, "cloud_servers")

    assert response.status_code == 200
    (resource,) = _version(response.json(), "v1")["resources"]
    assert resource["id"] == servers
    assert resource["name"] == "cloud_servers"
    assert _paths(resource["endpoints"]) == ["list_servers.rst", "create_server.rst"]
    # saved, not only answered
    assert laid_out.get(LAYOUT).json() == response.json()


def test_renaming_a_confirmed_resource_drops_only_its_confirmation(
    laid_out, session_factory
):
    """ADR-0068: the confirmation covered the old name, not the new one."""
    servers = _place(session_factory, "servers", [CREATE_SERVER], confirmed_by="val")
    _place(session_factory, "projects", [PROJECT_INFO], confirmed_by="val")

    body = _rename(laid_out, servers, "cloud_servers").json()

    renamed = _named(body, "v1", "cloud_servers")
    assert renamed["confirmed_by"] is None and renamed["confirmed_at"] is None
    assert _named(body, "v1", "projects")["confirmed_by"] == "val"


def test_renaming_a_resource_to_its_own_name_changes_nothing(laid_out, session_factory):
    servers = _place(session_factory, "servers", [CREATE_SERVER], confirmed_by="val")
    before = laid_out.get(LAYOUT).json()

    response = _rename(laid_out, servers, "servers")

    assert response.status_code == 200
    assert response.json() == before
    assert _named(before, "v1", "servers")["confirmed_by"] == "val"


@pytest.mark.parametrize("name", ["Servers", "os-keypairs", "2fa", "_servers", ""])
def test_a_name_that_is_no_package_name_is_invalid(laid_out, session_factory, name):
    """A malformed name is a bad request (422), not a conflict with the layout
    (409): it is refused before the layout is read."""
    servers = _place(session_factory, "servers", [CREATE_SERVER], confirmed_by="val")
    before = laid_out.get(LAYOUT).json()

    _refused(laid_out, _rename(laid_out, servers, name), 422, "validation failed")
    _refused(laid_out, _add(laid_out, name), 422, "validation failed")
    assert laid_out.get(LAYOUT).json() == before


def test_a_name_taken_in_the_version_is_refused(laid_out, session_factory):
    servers = _place(session_factory, "servers", [CREATE_SERVER])
    _place(session_factory, "projects", [PROJECT_INFO])
    before = laid_out.get(LAYOUT).json()

    response = _rename(laid_out, servers, "projects")

    _refused(laid_out, response, 409, "'projects' already exists in v1")
    assert laid_out.get(LAYOUT).json() == before


def test_a_name_taken_only_in_another_version_is_free(laid_out, session_factory):
    _place(session_factory, "servers", [CREATE_SERVER])
    tags = _place(session_factory, "tags", [LIST_TAGS], api_version="v2")

    response = _rename(laid_out, tags, "servers")

    assert response.status_code == 200
    assert _named(response.json(), "v2", "servers")["id"] == tags


def test_renaming_an_unknown_resource_is_not_found(laid_out, session_factory):
    _start_layout(session_factory)

    _refused(laid_out, _rename(laid_out, 999_999, "servers"), 404, "Resource 999999")


def test_renaming_a_resource_of_another_service_is_not_found(
    laid_out, session_factory, other_service
):
    _start_layout(session_factory)

    response = _rename(laid_out, other_service, "servers")

    _refused(laid_out, response, 404, f"Resource {other_service} not found")
    vpcs = _named(laid_out.get(_layout_of(OTHER_REPO)).json(), "v1", "vpcs")
    assert vpcs["id"] == other_service


def _layout_of(repo: str) -> str:
    return f"/api/generation/services/{repo}/layout"


# --- add -------------------------------------------------------------------


def test_a_resource_is_added_empty_to_a_version_the_layout_lists(
    laid_out, session_factory
):
    _start_layout(session_factory)

    response = _add(laid_out, "tags", api_version="v2")

    assert response.status_code == 201
    added = _named(response.json(), "v2", "tags")
    assert isinstance(added["id"], int)
    assert added["endpoints"] == []
    assert added["confirmed_by"] is None
    # the endpoints it could take are still where they were
    assert _paths(_version(response.json(), "v2")["unassigned"]) == ["list_tags.rst"]
    assert laid_out.get(LAYOUT).json() == response.json()


def test_a_resource_is_added_to_a_version_listed_by_its_resources_alone(
    laid_out, session_factory
):
    """Every v2 endpoint is placed, so v2 has no "unassigned" left; the layout
    read still lists it, and that is the condition."""
    _place(session_factory, "tags", [LIST_TAGS], api_version="v2")

    assert _add(laid_out, "labels", api_version="v2").status_code == 201


@pytest.mark.parametrize("api_version", ["v3", "", "V1"])
def test_a_resource_is_not_added_to_a_version_the_layout_does_not_list(
    laid_out, session_factory, api_version
):
    _start_layout(session_factory)
    before = laid_out.get(LAYOUT).json()

    response = _add(laid_out, "things", api_version=api_version)

    _refused(laid_out, response, 409, f"has no version {api_version}")
    assert laid_out.get(LAYOUT).json() == before


def test_an_added_resource_needs_a_package_name_free_in_its_version(
    laid_out, session_factory
):
    _place(session_factory, "servers", [CREATE_SERVER])
    before = laid_out.get(LAYOUT).json()

    _refused(laid_out, _add(laid_out, "Servers"), 422, "validation failed")
    _refused(laid_out, _add(laid_out, "servers"), 409, "already exists in v1")
    assert laid_out.get(LAYOUT).json() == before
    # the same name in another version is a different package
    assert _add(laid_out, "servers", api_version="v2").status_code == 201


# --- move ------------------------------------------------------------------


def test_an_unassigned_endpoint_moves_into_a_resource_of_its_version(
    laid_out, session_factory
):
    servers = _place(session_factory, "servers", [CREATE_SERVER])

    response = _move(laid_out, PROJECT_INFO.path, servers)

    assert response.status_code == 200
    body = response.json()
    assert _paths(_named(body, "v1", "servers")["endpoints"]) == [
        "project.rst",
        "create_server.rst",
    ]
    assert _paths(_version(body, "v1")["unassigned"]) == ["list_servers.rst"]
    assert laid_out.get(LAYOUT).json() == body


def test_an_unassigned_endpoint_does_not_move_into_another_version(
    laid_out, session_factory
):
    tags = _place(session_factory, "tags", [LIST_TAGS], api_version="v2")
    before = laid_out.get(LAYOUT).json()

    response = _move(laid_out, PROJECT_INFO.path, tags)

    _refused(laid_out, response, 409, "is in v1; it cannot move to resource tags in v2")
    assert laid_out.get(LAYOUT).json() == before


@pytest.mark.parametrize("api_version", ["v1", "v2"])
def test_an_endpoint_without_a_version_moves_into_a_resource_of_any_version(
    laid_out, session_factory, api_version
):
    """ADR-0059: the user sets the version the scanner did not find."""
    target = _place(session_factory, "quotas", [], api_version=api_version)

    body = _move(laid_out, QUOTAS.path, target).json()

    assert _paths(_named(body, api_version, "quotas")["endpoints"]) == ["quotas.rst"]
    assert body["no_version"] == []


def test_an_endpoint_moves_between_resources_of_one_version(laid_out, session_factory):
    servers = _place(session_factory, "servers", [CREATE_SERVER, LIST_SERVERS])
    projects = _place(session_factory, "projects", [PROJECT_INFO])

    body = _move(laid_out, CREATE_SERVER.path, projects).json()

    assert _paths(_named(body, "v1", "servers")["endpoints"]) == ["list_servers.rst"]
    assert _paths(_named(body, "v1", "projects")["endpoints"]) == [
        "project.rst",
        "create_server.rst",
    ]
    assert _named(body, "v1", "servers")["id"] == servers


def test_a_move_drops_the_confirmation_of_both_resources_and_no_other(
    laid_out, session_factory
):
    """ADR-0068: both resources now hold a set of endpoints nobody checked."""
    servers = _place(session_factory, "servers", [CREATE_SERVER], confirmed_by="val")
    projects = _place(session_factory, "projects", [PROJECT_INFO], confirmed_by="val")
    _place(session_factory, "lists", [LIST_SERVERS], confirmed_by="val")

    body = _move(laid_out, CREATE_SERVER.path, projects).json()

    assert _named(body, "v1", "servers")["id"] == servers
    for name in ("servers", "projects"):
        resource = _named(body, "v1", name)
        assert resource["confirmed_by"] is None and resource["confirmed_at"] is None
    assert _named(body, "v1", "lists")["confirmed_by"] == "val"


def test_moving_from_unassigned_drops_only_the_target_confirmation(
    laid_out, session_factory
):
    servers = _place(session_factory, "servers", [CREATE_SERVER], confirmed_by="val")
    _place(session_factory, "lists", [LIST_SERVERS], confirmed_by="val")

    body = _move(laid_out, PROJECT_INFO.path, servers).json()

    assert _named(body, "v1", "servers")["confirmed_by"] is None
    assert _named(body, "v1", "lists")["confirmed_by"] == "val"


def test_an_endpoint_in_a_resource_stays_in_that_resource_version(
    laid_out, session_factory
):
    """Once placed, an endpoint from "no version" has the version of its
    resource: it may not move on into another one."""
    quotas = _place(session_factory, "quotas", [QUOTAS], api_version="v2")
    servers = _place(session_factory, "servers", [CREATE_SERVER])
    before = laid_out.get(LAYOUT).json()

    response = _move(laid_out, QUOTAS.path, servers)

    _refused(laid_out, response, 409, "is in v2; it cannot move")
    assert laid_out.get(LAYOUT).json() == before
    assert _named(before, "v2", "quotas")["id"] == quotas


def test_moving_an_endpoint_into_its_own_resource_changes_nothing(
    laid_out, session_factory
):
    servers = _place(session_factory, "servers", [CREATE_SERVER], confirmed_by="val")
    before = laid_out.get(LAYOUT).json()

    response = _move(laid_out, CREATE_SERVER.path, servers)

    assert response.status_code == 200
    assert response.json() == before


def test_a_resource_whose_endpoints_all_moved_out_stays(laid_out, session_factory):
    servers = _place(session_factory, "servers", [CREATE_SERVER])
    projects = _place(session_factory, "projects", [])

    body = _move(laid_out, CREATE_SERVER.path, projects).json()

    emptied = _named(body, "v1", "servers")
    assert emptied["id"] == servers
    assert emptied["endpoints"] == []


@pytest.mark.parametrize(
    "path",
    [
        "api-ref/source/nothing_here.rst",
        # a document of the snapshot, but not an endpoint
        make_plain_document().path,
    ],
)
def test_moving_an_unknown_endpoint_is_not_found(laid_out, session_factory, path):
    _run_scan(
        session_factory,
        documents=[*LAYOUT_ENDPOINTS, make_plain_document()],
        commit_hash=NEXT_COMMIT,
    )
    servers = _place(session_factory, "servers", [CREATE_SERVER])
    before = laid_out.get(LAYOUT).json()

    _refused(laid_out, _move(laid_out, path, servers), 404, f"Endpoint {path}")
    assert laid_out.get(LAYOUT).json() == before


def test_moving_an_endpoint_of_another_service_is_not_found(
    laid_out, session_factory, other_service
):
    servers = _place(session_factory, "servers", [CREATE_SERVER])
    before = laid_out.get(LAYOUT).json()

    _refused(laid_out, _move(laid_out, VPC_ONLY.path, servers), 404, "not found")
    assert laid_out.get(LAYOUT).json() == before


def test_an_endpoint_the_active_snapshot_lacks_cannot_be_moved(
    laid_out, session_factory
):
    """Still linked to its resource, but not in what the layout shows."""
    servers = _place(session_factory, "servers", [CREATE_SERVER, LIST_SERVERS])
    projects = _place(session_factory, "projects", [PROJECT_INFO])
    _run_scan(
        session_factory,
        documents=[CREATE_SERVER, PROJECT_INFO],
        commit_hash=NEXT_COMMIT,
    )
    before = laid_out.get(LAYOUT).json()

    response = _move(laid_out, LIST_SERVERS.path, projects)

    _refused(laid_out, response, 404, "not found in the active snapshot")
    assert laid_out.get(LAYOUT).json() == before
    assert _named(before, "v1", "servers")["id"] == servers


def test_moving_into_an_unknown_resource_is_not_found(laid_out, session_factory):
    _start_layout(session_factory)
    before = laid_out.get(LAYOUT).json()

    response = _move(laid_out, PROJECT_INFO.path, 999_999)

    _refused(laid_out, response, 404, "Resource 999999")
    assert laid_out.get(LAYOUT).json() == before


def test_moving_into_a_resource_of_another_service_is_not_found(
    laid_out, session_factory, other_service
):
    _start_layout(session_factory)
    before = laid_out.get(LAYOUT).json()

    response = _move(laid_out, PROJECT_INFO.path, other_service)

    _refused(laid_out, response, 404, f"Resource {other_service} not found")
    assert laid_out.get(LAYOUT).json() == before
    other = laid_out.get(_layout_of(OTHER_REPO)).json()
    assert _paths(_named(other, "v1", "vpcs")["endpoints"]) == ["list_vpcs.rst"]


# --- confirm ---------------------------------------------------------------


def _ok(endpoint):
    """``endpoint`` read in full: every section ``ok``, so its status is ``ok``."""
    return endpoint.model_copy(
        update={
            "sections": [
                section.model_copy(
                    update={
                        "scan_result": section.scan_result.model_copy(
                            update={"status": SectionStatus.OK, "issues": []}
                        )
                    }
                )
                if section.scan_result is not None
                else section
                for section in endpoint.sections
            ]
        }
    )


#: Two endpoints read in full; PROJECT_INFO, LIST_TAGS and QUOTAS stay partial.
OK_CREATE_SERVER = _ok(CREATE_SERVER)
OK_LIST_SERVERS = _ok(LIST_SERVERS)


@pytest.fixture
def ready(client, session_factory):
    """REPO scanned with two endpoints ``ok`` and three ``partial``."""
    _register(session_factory)
    _run_scan(
        session_factory,
        documents=[OK_CREATE_SERVER, OK_LIST_SERVERS, PROJECT_INFO, LIST_TAGS, QUOTAS],
    )
    return client


def _confirm(client, resource_id: int, repo: str = REPO):
    return client.post(
        f"/api/generation/services/{repo}/layout/resources/{resource_id}/confirm"
    )


def test_a_resource_with_every_endpoint_ok_is_confirmed_by_the_caller(
    ready, session_factory
):
    servers = _place(session_factory, "servers", [OK_CREATE_SERVER, OK_LIST_SERVERS])
    before = datetime.now(tz=UTC)

    response = _confirm(ready, servers)

    assert response.status_code == 200
    confirmed = _named(response.json(), "v1", "servers")
    assert confirmed["confirmed_by"] == TEST_WORKER.name
    at = datetime.fromisoformat(confirmed["confirmed_at"])
    assert before <= at <= datetime.now(tz=UTC)
    # the layout read serves it as saved
    assert response.json() == ready.get(LAYOUT).json()
    assert [e["overall_status"] for e in confirmed["endpoints"]] == ["ok", "ok"]


def test_confirming_one_resource_leaves_every_other_as_it_was(ready, session_factory):
    """ADR-0066: each resource is confirmed on its own."""
    servers = _place(session_factory, "servers", [OK_CREATE_SERVER])
    _place(session_factory, "lists", [OK_LIST_SERVERS])
    _place(session_factory, "projects", [PROJECT_INFO], confirmed_by="val")

    body = _confirm(ready, servers).json()

    assert _named(body, "v1", "servers")["confirmed_by"] == TEST_WORKER.name
    assert _named(body, "v1", "lists")["confirmed_by"] is None
    projects = _named(body, "v1", "projects")
    assert projects["confirmed_by"] == "val"
    assert projects["confirmed_at"].startswith("2026-11-03")


def test_a_resource_with_an_endpoint_not_ok_is_refused_and_nothing_changes(
    ready, session_factory
):
    """ADR-0067: one endpoint not ``ok`` blocks its own resource, no other."""
    servers = _place(session_factory, "servers", [OK_CREATE_SERVER, PROJECT_INFO])
    lists = _place(session_factory, "lists", [OK_LIST_SERVERS])
    before = ready.get(LAYOUT).json()

    response = _confirm(ready, servers)

    _refused(ready, response, 409, PROJECT_INFO.path)
    assert OK_CREATE_SERVER.path not in response.json()["error"]["message"]
    assert ready.get(LAYOUT).json() == before
    assert _confirm(ready, lists).status_code == 200


@pytest.mark.parametrize("content", ["no endpoint", "a path the snapshot lacks"])
def test_a_resource_without_an_endpoint_in_the_active_snapshot_is_refused(
    ready, session_factory, content
):
    endpoints = (
        []
        if content == "no endpoint"
        else [_endpoint("gone.rst", "GET", "/v1/x", "v1")]
    )
    empty = _place(session_factory, "empty", endpoints)

    response = _confirm(ready, empty)

    _refused(ready, response, 409, "has no endpoint in the active snapshot")
    assert _named(ready.get(LAYOUT).json(), "v1", "empty")["confirmed_by"] is None


def test_a_path_the_active_snapshot_lacks_is_neither_checked_nor_blocking(
    ready, session_factory
):
    """What the layout read does not show cannot be checked, or moved out of
    the resource: it neither counts as an endpoint nor blocks the others."""
    servers = _place(
        session_factory,
        "servers",
        [OK_CREATE_SERVER, _endpoint("gone.rst", "GET", "/v1/gone", "v1")],
    )

    assert _confirm(ready, servers).status_code == 200


def test_only_the_active_snapshot_decides(client, session_factory):
    """An older snapshot's statuses - of an endpoint since read in full, or of
    one since gone - are not the endpoints the layout read shows."""
    gone = _endpoint("gone.rst", "GET", "/v1/gone", "v1")
    _register(session_factory)
    _run_scan(session_factory, documents=[CREATE_SERVER, gone])
    _run_scan(session_factory, documents=[OK_CREATE_SERVER], commit_hash=NEXT_COMMIT)
    servers = _place(session_factory, "servers", [OK_CREATE_SERVER, gone])

    assert _confirm(client, servers).status_code == 200


def test_confirming_a_confirmed_resource_keeps_the_first_confirmation(
    ready, session_factory
):
    servers = _place(session_factory, "servers", [OK_CREATE_SERVER], confirmed_by="val")
    before = ready.get(LAYOUT).json()

    response = _confirm(ready, servers)

    assert response.status_code == 200
    assert response.json() == before
    kept = _named(response.json(), "v1", "servers")
    assert kept["confirmed_by"] == "val"
    assert kept["confirmed_at"].startswith("2026-11-03")


@pytest.mark.parametrize("whose", ["unknown", "another service's"])
def test_confirming_a_resource_the_layout_lacks_is_not_found(
    laid_out, session_factory, other_service, whose
):
    _place(session_factory, "servers", [CREATE_SERVER])
    resource_id = 999_999 if whose == "unknown" else other_service

    _refused(
        laid_out,
        _confirm(laid_out, resource_id),
        404,
        f"Resource {resource_id} not found",
    )


def test_a_confirmation_is_refused_for_a_service_without_a_layout(ready):
    _refused(ready, _confirm(ready, 1), 409, "has no layout yet")


def test_an_edit_after_a_confirmation_asks_for_a_new_check(ready, session_factory):
    """ADR-0068: the confirmation covered exactly the endpoints it checked. A
    move from "unassigned" brings one it did not, so it is dropped - and the
    new check refuses, as that endpoint is not ``ok``."""
    servers = _place(session_factory, "servers", [OK_CREATE_SERVER])
    assert _confirm(ready, servers).status_code == 200

    moved = _move(ready, PROJECT_INFO.path, servers).json()

    assert _named(moved, "v1", "servers")["confirmed_by"] is None
    _refused(ready, _confirm(ready, servers), 409, PROJECT_INFO.path)


def test_a_refusal_counts_what_blocks_and_names_the_first_few(client, session_factory):
    blocking = [
        _endpoint(f"partial_{n}.rst", "GET", f"/v1/thing{n}", "v1") for n in range(7)
    ]
    _register(session_factory)
    _run_scan(session_factory, documents=blocking)
    things = _place(session_factory, "things", blocking)

    message = _confirm(client, things).json()["error"]["message"]

    assert "7 endpoint(s) that are not ok" in message
    assert message.endswith("and 2 more")
    assert sum(endpoint.path in message for endpoint in blocking) == 5


# --- a snapshot change ------------------------------------------------------


def _confirmed(client) -> dict[str, str | None]:
    return {
        resource["name"]: resource["confirmed_by"]
        for version in client.get(LAYOUT).json()["versions"]
        for resource in version["resources"]
    }


def test_a_rescan_that_takes_an_endpoint_away_drops_that_confirmation_only(
    ready, session_factory
):
    """ADR-0068: a confirmation covers the endpoints it checked. One gone,
    the resource is another set; a resource whose set stays keeps its own."""
    _place(session_factory, "servers", [OK_CREATE_SERVER], confirmed_by="val")
    _place(session_factory, "lists", [OK_LIST_SERVERS], confirmed_by="val")

    _run_scan(session_factory, documents=[OK_CREATE_SERVER], commit_hash=NEXT_COMMIT)

    assert _confirmed(ready) == {"servers": "val", "lists": None}


def test_a_rescan_that_keeps_the_endpoints_ok_keeps_the_confirmation(
    ready, session_factory
):
    _place(session_factory, "servers", [OK_CREATE_SERVER], confirmed_by="val")

    _run_scan(
        session_factory,
        documents=[OK_CREATE_SERVER, OK_LIST_SERVERS],
        commit_hash=NEXT_COMMIT,
    )

    assert _confirmed(ready) == {"servers": "val"}


def test_a_rescan_that_leaves_an_endpoint_not_ok_drops_that_confirmation_only(
    ready, session_factory
):
    """ADR-0067: only a resource whose endpoints are all ``ok`` is confirmed.
    The set stays, but one endpoint is read as ``partial`` now."""
    _place(session_factory, "servers", [OK_CREATE_SERVER], confirmed_by="val")
    _place(session_factory, "lists", [OK_LIST_SERVERS], confirmed_by="val")

    _run_scan(
        session_factory,
        documents=[CREATE_SERVER, OK_LIST_SERVERS],
        commit_hash=NEXT_COMMIT,
    )

    assert _confirmed(ready) == {"servers": None, "lists": "val"}


def test_activating_a_snapshot_that_reads_an_endpoint_as_not_ok_drops_it(
    client, session_factory
):
    _register(session_factory)
    _run_scan(session_factory, documents=[CREATE_SERVER, OK_LIST_SERVERS])
    _run_scan(
        session_factory,
        documents=[OK_CREATE_SERVER, OK_LIST_SERVERS],
        commit_hash=NEXT_COMMIT,
    )
    _place(session_factory, "servers", [OK_CREATE_SERVER], confirmed_by="val")
    _place(session_factory, "lists", [OK_LIST_SERVERS], confirmed_by="val")
    with session_factory() as session:
        first = session.scalars(select(Snapshot.id).order_by(Snapshot.id)).first()

    assert _activate(client, first).status_code == 200

    assert _confirmed(client) == {"servers": None, "lists": "val"}


def test_activating_a_snapshot_that_brings_back_a_hidden_endpoint_drops_it(
    client, session_factory
):
    """A stored path the confirmation never saw comes back with an older
    snapshot: the resource then holds an endpoint nobody checked."""
    gone = _endpoint("gone.rst", "GET", "/v1/gone", "v1")
    _register(session_factory)
    _run_scan(session_factory, documents=[OK_CREATE_SERVER, OK_LIST_SERVERS, gone])
    _run_scan(
        session_factory,
        documents=[OK_CREATE_SERVER, OK_LIST_SERVERS],
        commit_hash=NEXT_COMMIT,
    )
    _place(session_factory, "servers", [OK_CREATE_SERVER, gone], confirmed_by="val")
    _place(session_factory, "lists", [OK_LIST_SERVERS], confirmed_by="val")
    with session_factory() as session:
        first = session.scalars(select(Snapshot.id).order_by(Snapshot.id)).first()

    assert _activate(client, first).status_code == 200

    assert _confirmed(client) == {"servers": None, "lists": "val"}


def test_moving_the_active_snapshot_takes_the_service_lock_itself(
    ready, session_factory, impatient_engine
):
    """Ingest locks only its Job: the Service row must be locked by the move
    itself, or a confirmation written meanwhile would outlive the switch.
    Shown with a move that changes nothing else, so only its own lock waits."""
    with session_factory() as holder:
        holder.scalar(select(Service).where(Service.repo == REPO).with_for_update())

        with sessionmaker(bind=impatient_engine)() as mover:
            service = mover.scalar(select(Service).where(Service.repo == REPO))
            with pytest.raises(OperationalError, match="lock timeout"):
                layout_module.switch_active_snapshot(
                    mover, service, service.active_snapshot_id
                )


def test_the_check_and_the_confirmation_happen_while_the_service_is_locked(
    ready, session_factory, monkeypatch
):
    """An edit, an ingest or an activation takes the same lock, so none can
    change the endpoints between their check and the confirmation written for
    them - proven by failing to take the lock from a second session."""
    servers = _place(session_factory, "servers", [OK_CREATE_SERVER])
    locked: list[bool] = []
    statuses = generation.endpoint_statuses

    def checking(db, service, resource):
        with session_factory() as other:
            try:
                other.scalar(
                    select(Service)
                    .where(Service.repo == REPO)
                    .with_for_update(nowait=True)
                )
                locked.append(False)
            except OperationalError:
                locked.append(True)
        return statuses(db, service, resource)

    monkeypatch.setattr(generation, "endpoint_statuses", checking)

    assert _confirm(ready, servers).status_code == 200
    assert locked == [True]


# --- every edit ------------------------------------------------------------


def _every_edit(client, resource_id: int):
    return [
        _add(client, "things"),
        _rename(client, resource_id, "things"),
        _move(client, PROJECT_INFO.path, resource_id),
    ]


def test_no_edit_reaches_a_service_whose_grouping_has_not_run(laid_out):
    """A layout starts only from the preliminary grouping, not from an edit."""
    for response in _every_edit(laid_out, 1):
        _refused(laid_out, response, 409, "has no layout yet")
    assert laid_out.get(LAYOUT).json()["has_layout"] is False


def test_no_edit_reaches_a_repository_never_registered(client):
    for response in _every_edit(client, 1):
        _refused(client, response, 404, "Service not found")


def test_no_edit_reaches_an_excluded_service(laid_out, session_factory):
    servers = _place(session_factory, "servers", [CREATE_SERVER])
    assert _exclude(laid_out).status_code == 204

    for response in _every_edit(laid_out, servers):
        _refused(laid_out, response, 404, "Service not found")

    assert laid_out.post(f"/api/scan/services/{REPO}/include").status_code == 204
    (resource,) = laid_out.get(LAYOUT).json()["versions"][0]["resources"]
    assert resource["name"] == "servers"
    assert _paths(resource["endpoints"]) == ["create_server.rst"]


def test_no_edit_reaches_an_ineligible_repository(laid_out, session_factory):
    servers = _place(session_factory, "servers", [CREATE_SERVER])
    _set_eligibility(session_factory, REPO, False)

    for response in _every_edit(laid_out, servers):
        _refused(laid_out, response, 404, "Service not found")


def test_no_edit_reaches_a_service_without_endpoints(client, session_factory):
    _register(session_factory)
    _run_scan(session_factory, documents=[_page_without_endpoints()])
    _start_layout(session_factory)

    for response in _every_edit(client, 1):
        _refused(client, response, 404, "Service not found")


def test_listed_versions_are_the_versions_the_layout_read_lists(
    laid_out, session_factory
):
    """The add check reads versions from columns alone; it must agree with
    the read in every way a version gets listed - or does not."""
    # v2's only endpoint linked into a v1 resource, as a rescan that changed
    # its version leaves it: placed, so it no longer lists v2
    _place(session_factory, "tags", [LIST_TAGS], api_version="v1")
    _place(session_factory, "spare", [], api_version="v4")  # an empty resource
    # v1 keeps PROJECT_INFO and the servers in "unassigned"; QUOTAS stays in
    # "no version", which is no version to list

    read = {v["api_version"] for v in laid_out.get(LAYOUT).json()["versions"]}
    with session_factory() as session:
        service = session.scalar(select(Service).where(Service.repo == REPO))
        listed = listed_versions(session, service)

    assert listed == read == {"v1", "v4"}


class _Diagnostics:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _DriverError(Exception):
    """What a PostgreSQL driver hands SQLAlchemy as ``IntegrityError.orig``."""

    def __init__(self, constraint_name: str | None = None) -> None:
        super().__init__("integrity error")
        if constraint_name is not None:
            self.diag = _Diagnostics(constraint_name)


class _FailingSave:
    """A session whose flush or commit breaks a constraint, recording each call."""

    def __init__(self, error: IntegrityError, *, on: str) -> None:
        self.error = error
        self.on = on
        self.calls: list[str] = []

    def flush(self) -> None:
        self.calls.append("flush")
        if self.on == "flush":
            raise self.error

    def expire_all(self) -> None:
        self.calls.append("expire_all")

    def commit(self) -> None:
        self.calls.append("commit")
        if self.on == "commit":
            raise self.error

    def rollback(self) -> None:
        self.calls.append("rollback")


@pytest.mark.parametrize(
    "orig",
    [
        _DriverError("fk_resource_service_id_layout"),
        # a driver that reports no constraint name at all
        _DriverError(),
    ],
)
@pytest.mark.parametrize("on", ["flush", "commit"])
def test_a_violation_that_is_not_the_name_is_no_refusal(monkeypatch, orig, on):
    """Only a taken name is the request's to fix; anything else is a server
    fault and must surface as one, not as a 409 blaming the name. A reply built
    before a commit that then fails is dropped, never returned."""
    monkeypatch.setattr(generation, "_layout", lambda db, service: "the reply")
    error = IntegrityError("UPDATE resource", {}, orig)
    db = _FailingSave(error, on=on)

    with pytest.raises(IntegrityError) as raised:
        generation._save(db, Service(), name="servers", api_version="v1")

    assert raised.value is error
    assert db.calls[-1] == "rollback"


def test_a_taken_name_is_refused_only_for_an_edit_that_names_one(monkeypatch):
    """A move writes no name, so even the unique name constraint is no
    refusal of it: only an add or a rename can have picked a taken name."""
    monkeypatch.setattr(generation, "_layout", lambda db, service: "the reply")
    error = IntegrityError(
        "INSERT resource_endpoint",
        {},
        _DriverError(RESOURCE_NAME_UNIQUE_IN_VERSION.name),
    )

    with pytest.raises(IntegrityError):
        generation._save(_FailingSave(error, on="flush"), Service())


def test_the_reply_is_read_before_the_commit(monkeypatch):
    monkeypatch.setattr(generation, "_layout", lambda db, service: "the reply")
    db = _FailingSave(IntegrityError("", {}, _DriverError()), on="neither")

    reply = generation._save(db, Service())

    assert reply == "the reply"
    assert db.calls == ["flush", "expire_all", "commit"]


@pytest.mark.parametrize(
    "edit",
    [
        "start",
        "add",
        "rename",
        "move",
        "rename to its name",
        "move into its resource",
    ],
)
def test_every_reply_is_read_while_the_service_is_locked(
    laid_out, session_factory, monkeypatch, edit
):
    """Read after the lock is gone, the reply's several queries could each see
    a different edit of another worker. So the layout is read back while the
    row is still held - proven by failing to take it from a second session.
    The layout start answers the same way."""
    servers = (
        None if edit == "start" else _place(session_factory, "servers", [CREATE_SERVER])
    )
    locked_while_read: list[bool] = []
    read_layout = generation.service_layout

    def reading(db, service):
        with session_factory() as other:
            try:
                other.scalar(
                    select(Service)
                    .where(Service.repo == REPO)
                    .with_for_update(nowait=True)
                )
                locked_while_read.append(False)
            except OperationalError:
                locked_while_read.append(True)
        return read_layout(db, service)

    monkeypatch.setattr(generation, "service_layout", reading)

    response = {
        "start": lambda: laid_out.post(LAYOUT),
        "add": lambda: _add(laid_out, "projects"),
        "rename": lambda: _rename(laid_out, servers, "cloud_servers"),
        "move": lambda: _move(laid_out, PROJECT_INFO.path, servers),
        "rename to its name": lambda: _rename(laid_out, servers, "servers"),
        "move into its resource": lambda: _move(laid_out, CREATE_SERVER.path, servers),
    }[edit]()

    assert response.status_code in (200, 201)
    assert locked_while_read == [True]
    # and what was read is what was saved
    monkeypatch.setattr(generation, "service_layout", read_layout)
    assert response.json() == laid_out.get(LAYOUT).json()


@pytest.fixture
def impatient_engine(engine):
    """The scratch database again, giving up on a row lock after 200 ms."""
    eng = create_engine(
        engine.url.render_as_string(hide_password=False),
        connect_args={"options": "-c lock_timeout=200"},
    )
    yield eng
    eng.dispose()


def test_a_scan_landing_mid_edit_waits_for_the_edit_to_commit(
    laid_out, session_factory, impatient_engine, monkeypatch
):
    """An edit checks an endpoint against the active Snapshot while holding the
    Service row; ingest replaces that Snapshot by writing the row, so it cannot
    slip in between. Proven by holding the row as an edit does: ingest, given a
    short lock timeout, gives up instead of going ahead."""
    monkeypatch.setattr(
        ingest_module, "SessionLocal", sessionmaker(bind=impatient_engine)
    )
    _start_layout(session_factory)

    with session_factory() as session:
        job = RepositoryScanJob(
            service_id=session.scalar(select(Service.id).where(Service.repo == REPO)),
            kind=JobKind.scan,
            status=JobStatus.running,
            initiated_by="tester",
            started_at=datetime.now(tz=UTC),
        )
        session.add(job)
        session.commit()
        job_id = job.id
    result = RepositoryScanResult(
        repository=IrService(repo=REPO, documents=[CREATE_SERVER]),
        branch="main",
        commit_hash=NEXT_COMMIT,
    )

    with session_factory() as edit:
        generation._editable_service(edit, REPO)

        with pytest.raises(OperationalError, match="lock timeout"):
            ingest_service_result(job_id=job_id, service_repo=REPO, result=result)

    snapshots = laid_out.get(f"/api/scan/services/{REPO}/snapshots").json()["items"]
    assert [snapshot["commit_hash"] for snapshot in snapshots] == [COMMIT]


@pytest.mark.parametrize("edit", ["rename", "move"])
def test_an_edit_that_changes_nothing_holds_no_lock_while_it_answers(
    laid_out, session_factory, edit
):
    """An edit that writes nothing still ends its transaction once it has its
    answer, so a scan or another edit can take the row at once."""
    servers = _place(session_factory, "servers", [CREATE_SERVER])

    with session_factory() as db:
        if edit == "rename":
            generation.rename_resource(
                REPO,
                servers,
                RenameResourceRequest(name="servers"),
                identity=TEST_WORKER,
                db=db,
            )
        else:
            generation.move_endpoint(
                REPO,
                MoveEndpointRequest(path=CREATE_SERVER.path, resource_id=servers),
                identity=TEST_WORKER,
                db=db,
            )

        with session_factory() as other:
            other.scalar(
                select(Service).where(Service.repo == REPO).with_for_update(nowait=True)
            )


#: An endpoint whose version the scanner left empty rather than missing.
BLANK_VERSION = _endpoint("blank.rst", "GET", "/{project_id}/blank", "")


def test_an_empty_version_is_no_version_in_the_read_and_the_edits(
    client, session_factory
):
    """The grouping puts `api_version=""` in "no version"; the read, the version
    listing and a move must agree, or such an endpoint would be in "no version"
    for one and under a nameless version for another."""
    _register(session_factory)
    _run_scan(session_factory, documents=[*LAYOUT_ENDPOINTS, BLANK_VERSION])
    servers = _place(session_factory, "servers", [CREATE_SERVER])

    body = client.get(LAYOUT).json()
    assert _paths(body["no_version"]) == ["blank.rst", "quotas.rst"]
    assert [v["api_version"] for v in body["versions"]] == ["v1", "v2"]
    with session_factory() as session:
        service = session.scalar(select(Service).where(Service.repo == REPO))
        assert listed_versions(session, service) == {"v1", "v2"}

    response = _move(client, BLANK_VERSION.path, servers)

    assert response.status_code == 200
    moved = response.json()
    # ordered by URI, as the read orders every list
    assert _paths(_named(moved, "v1", "servers")["endpoints"]) == [
        "create_server.rst",
        "blank.rst",
    ]
    assert _paths(moved["no_version"]) == ["quotas.rst"]
