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
from tools.panel.api.auth import Identity, PanelRole, current_identity  # noqa: E402
from tools.panel.core import ingest as ingest_module  # noqa: E402
from tools.panel.core.db.models import (  # noqa: E402
    TERMINAL_JOB_STATUSES,
    DocumentRecord,
    ExcludedService,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
    Snapshot,
)
from tools.panel.core.ingest import ingest_service_result  # noqa: E402
from tools.shared.ir import Service as IrService  # noqa: E402
from tools.shared.scan import RepositoryScanResult  # noqa: E402

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


def _set_head(session_factory, commit: str, repo: str = REPO) -> None:
    """What discovery writes when it resolves the branch HEAD (PS2-4)."""
    with session_factory() as session:
        service = session.scalar(select(Service).where(Service.repo == repo))
        service.head_commit = commit
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
