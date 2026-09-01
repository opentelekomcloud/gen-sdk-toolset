"""API tests for scan launch and job polling.

Reuses the PostgreSQL provisioning from tests/test_panel_db.py, so this module
is skipped unless TEST_DATABASE_URL is set or Docker is available (see that
module's docstring).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")
pytest.importorskip("alembic")
pytest.importorskip("httpx")  # required by fastapi.testclient.TestClient

from alembic import command  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from tests.test_panel_db import (  # noqa: E402,F401  (reused DB fixtures)
    _alembic_config,
    admin_url,
    make_endpoint,
    scratch_database,
)
from tools import __version__ as SCANNER_VERSION  # noqa: E402
from tools.panel.api import app as app_module  # noqa: E402
from tools.panel.api import deps  # noqa: E402
from tools.panel.api.app import create_app  # noqa: E402
from tools.panel.api.auth import Identity, PanelRole, current_identity  # noqa: E402
from tools.panel.api.routes import scans as scans_module  # noqa: E402
from tools.panel.core import ingest as ingest_module  # noqa: E402
from tools.panel.core import jobs as jobs_module  # noqa: E402
from tools.panel.core.db.models import (  # noqa: E402
    ExcludedService,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
    Snapshot,
)
from tools.shared.ir import Repository  # noqa: E402
from tools.shared.ir import Service as IrService
from tools.shared.scan import (  # noqa: E402
    RepositoryInterruption,
    RepositoryInterruptionKind,
    RepositoryScanResult,
)

#: The caller the API tests act as. Deliberately not the name any request body
#: sends, so an assertion on `initiated_by` fails if the body ever wins again.
TEST_WORKER = Identity(
    subject="tester-subject",
    name="test-worker",
    roles=frozenset({PanelRole.worker}),
)


@pytest.fixture
def engine(scratch_database):  # noqa: F811  (pytest fixture injection, not a redefinition)
    url = scratch_database("panel_test_scan_job")
    command.upgrade(_alembic_config(url), "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
def client(session_factory, monkeypatch):
    """TestClient whose API and background runner both use the scratch DB."""
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
    # The runner opens its own SessionLocal and would bind the real engine via
    # get_engine(); point both at the test database instead.
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    monkeypatch.setattr(jobs_module, "get_engine", lambda: None)
    return TestClient(app)


def _seed_service(
    session_factory, repo: str, *, name: str = "svc", branch: str = "main"
) -> int:
    with session_factory() as s:
        service = Service(repo=repo, name=name, branch=branch)
        s.add(service)
        s.commit()
        s.refresh(service)
        return service.id


def test_launch_returns_job_id_and_runs_to_running(
    client, session_factory, monkeypatch
):
    service_id = _seed_service(session_factory, "elb-api")

    seen = {}

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                seen["repo"] = repo
                seen["branch"] = branch
                return RepositoryScanResult(
                    repository=IrService(repo=repo),
                    branch=branch,
                    commit_hash="c0ffee",
                )

        return _Scanner()

    spy = {}

    def fake_ingest(*, job_id, service_repo, result):
        spy["job_id"] = job_id
        spy["service_repo"] = service_repo
        spy["result"] = result

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(jobs_module, "ingest_service_result", fake_ingest)

    resp = client.post(
        "/api/scan/services/elb-api/rescan", json={"initiated_by": "tester"}
    )

    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # TestClient runs the BackgroundTask after the response is returned.
    assert seen == {"repo": "elb-api", "branch": "main"}
    assert spy["job_id"] == job_id
    assert spy["service_repo"] == "elb-api"
    assert spy["result"].commit_hash == "c0ffee"

    with session_factory() as s:
        job = s.get(RepositoryScanJob, job_id)
        assert job.service_id == service_id
        assert job.status is JobStatus.running
        assert job.started_at is not None
        assert job.finished_at is None
        # From the token, not from the body, which said "tester".
        assert job.initiated_by == TEST_WORKER.name


def test_get_job_returns_full_polling_shape(client, session_factory):
    service_id = _seed_service(session_factory, "kms-api", name="kms")
    with session_factory() as s:
        job = RepositoryScanJob(
            service_id=service_id,
            kind=JobKind.scan,
            status=JobStatus.queued,
            initiated_by="tester",
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        job_id = job.id

    resp = client.get(f"/api/jobs/{job_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {
        "id",
        "service_id",
        "repository",
        "kind",
        "status",
        "scanner_version",
        "commit_hash",
        "error",
        "created_at",
        "started_at",
        "finished_at",
    }
    assert body["id"] == job_id
    assert body["service_id"] == service_id
    assert body["repository"] == "kms-api"
    assert body["kind"] == "scan"
    assert body["status"] == "queued"
    assert body["scanner_version"] is None  # no snapshot until ingest
    assert body["commit_hash"] is None
    assert body["error"] is None
    assert body["started_at"] is None
    assert body["finished_at"] is None


def test_launch_unknown_service_returns_404(client):
    resp = client.post(
        "/api/scan/services/does-not-exist/rescan", json={"initiated_by": "t"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_get_unknown_job_returns_404(client):
    resp = client.get("/api/jobs/999999")
    assert resp.status_code == 404


def test_second_active_scan_conflicts_409(client, session_factory):
    service_id = _seed_service(session_factory, "vpc-api", name="vpc")
    with session_factory() as s:  # an already-active queued scan for the service
        active = RepositoryScanJob(
            service_id=service_id,
            kind=JobKind.scan,
            status=JobStatus.queued,
            initiated_by="someone",
        )
        s.add(active)
        s.commit()
        s.refresh(active)
        active_id = active.id

    resp = client.post(
        "/api/scan/services/vpc-api/rescan", json={"initiated_by": "tester"}
    )

    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "conflict"
    assert f"#{active_id}" in body["error"]["message"]  # names the blocking job
    assert "queued" in body["error"]["message"]
    with session_factory() as s:  # the unique index held: still one job
        jobs = s.scalars(
            select(RepositoryScanJob).where(RepositoryScanJob.service_id == service_id)
        ).all()
        assert len(jobs) == 1


def test_job_service_relationship(client, session_factory):
    service_id = _seed_service(session_factory, "dns-api", name="dns")
    with session_factory() as s:
        job = RepositoryScanJob(
            service_id=service_id, kind=JobKind.scan, status=JobStatus.queued
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        assert job.service.repo == "dns-api"
        assert job.id in [j.id for j in job.service.jobs]


def test_scan_failure_marks_job_failed(client, session_factory, monkeypatch):
    _seed_service(session_factory, "obs-api", name="obs")

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                return RepositoryScanResult(
                    repository=Repository(repo=repo),
                    branch=branch,
                    error="boom: could not resolve commit",
                )

        return _Scanner()

    called = {"ingest": False}

    def fake_ingest(**_kwargs):
        called["ingest"] = True

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(jobs_module, "ingest_service_result", fake_ingest)

    resp = client.post(
        "/api/scan/services/obs-api/rescan", json={"initiated_by": "tester"}
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    assert called["ingest"] is False  # a failed scan is never ingested
    with session_factory() as s:
        job = s.get(RepositoryScanJob, job_id)
        assert job.status is JobStatus.failed
        assert job.error == "boom: could not resolve commit"
        assert job.finished_at is not None


def test_ingest_failure_marks_job_failed(client, session_factory, monkeypatch):
    _seed_service(session_factory, "ims-api", name="ims")

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                return RepositoryScanResult(
                    repository=IrService(repo=repo), branch=branch, commit_hash="abc"
                )

        return _Scanner()

    def boom_ingest(**_kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(jobs_module, "ingest_service_result", boom_ingest)

    resp = client.post(
        "/api/scan/services/ims-api/rescan", json={"initiated_by": "tester"}
    )
    job_id = resp.json()["job_id"]

    with session_factory() as s:
        job = s.get(RepositoryScanJob, job_id)
        assert job.status is JobStatus.failed
        assert "ingest failed" in job.error
        assert job.finished_at is not None


def test_launch_requires_non_empty_initiated_by(client, session_factory):
    _seed_service(session_factory, "nat-api", name="nat")
    resp = client.post("/api/scan/services/nat-api/rescan", json={"initiated_by": ""})
    assert resp.status_code == 422


def test_launch_resolves_service_by_repo_with_slash(
    client, session_factory, monkeypatch
):
    """The URL segment carries ``Service.repo`` (which may contain ``/``), not
    the display name — seeded with repo != name so a name-based lookup cannot
    pass by accident."""
    _seed_service(session_factory, "opentelekomcloud-docs/elb-api", name="elb-api")

    seen = {}

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                seen["repo"] = repo
                return RepositoryScanResult(
                    repository=IrService(repo=repo), branch=branch, commit_hash="c0ffee"
                )

        return _Scanner()

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(jobs_module, "ingest_service_result", lambda **_kwargs: None)

    resp = client.post(
        "/api/scan/services/opentelekomcloud-docs/elb-api/rescan",
        json={"initiated_by": "tester"},
    )

    assert resp.status_code == 202
    assert seen["repo"] == "opentelekomcloud-docs/elb-api"


def test_scan_interruption_marks_job_failed_with_payload(
    client, session_factory, monkeypatch
):
    _seed_service(session_factory, "cce-api", name="cce")

    interruption = RepositoryInterruption(
        kind=RepositoryInterruptionKind.rate_limit,
        repository="cce-api",
        message="rate limit exceeded",
        reset_time=1234,
    )

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                return RepositoryScanResult(
                    repository=Repository(repo=repo),
                    branch=branch,
                    interruption=interruption,
                )

        return _Scanner()

    called = {"ingest": False}

    def fake_ingest(**_kwargs):
        called["ingest"] = True

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(jobs_module, "ingest_service_result", fake_ingest)

    resp = client.post(
        "/api/scan/services/cce-api/rescan", json={"initiated_by": "tester"}
    )
    job_id = resp.json()["job_id"]

    assert called["ingest"] is False  # an interrupted scan is never ingested
    with session_factory() as s:
        job = s.get(RepositoryScanJob, job_id)
        assert job.status is JobStatus.failed
        assert job.error == "rate limit exceeded"
        assert job.finished_at is not None
        assert job.interruption == {
            "kind": "rate_limit",
            "repository": "cce-api",
            "message": "rate limit exceeded",
            "reset_time": 1234,
        }


def test_interruption_payload_covers_every_dataclass_field():
    """A field added to RepositoryInterruption must reach the JSONB payload —
    guards the asdict serialization against silent drops."""
    result = RepositoryScanResult(
        repository=Repository(repo="r"),
        branch="main",
        interruption=RepositoryInterruption(
            kind=RepositoryInterruptionKind.rate_limit,
            repository="r",
            message="m",
            reset_time=1,
        ),
    )

    payload = jobs_module._interruption_payload(result)

    assert payload is not None
    assert set(payload) == {f.name for f in dataclasses.fields(RepositoryInterruption)}
    assert payload["kind"] == "rate_limit"


def test_runner_skips_job_not_in_queued_state(client, session_factory, monkeypatch):
    """A double-scheduled runner never scans the same job twice."""
    service_id = _seed_service(session_factory, "smn-api", name="smn")
    with session_factory() as s:
        job = RepositoryScanJob(
            service_id=service_id,
            kind=JobKind.scan,
            status=JobStatus.running,
            started_at=datetime.now(tz=UTC),
            initiated_by="tester",
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        job_id = job.id

    def explode(_settings):
        raise AssertionError("scanner must not be built for a non-queued job")

    monkeypatch.setattr(jobs_module, "build_scanner", explode)

    jobs_module.run_scan_job(job_id)

    with session_factory() as s:
        job = s.get(RepositoryScanJob, job_id)
        assert job.status is JobStatus.running  # untouched, not re-run
        assert job.finished_at is None


def test_failed_start_transition_marks_job_failed_not_stuck_queued(
    client, session_factory, monkeypatch
):
    """If the queued->running commit fails, the Job must still reach a terminal
    state — a Job stuck in ``queued`` blocks its service forever via
    uq_active_scan_job_per_service."""
    _seed_service(session_factory, "dds-api", name="dds")

    state = {"armed": True}

    def flaky_session_factory():
        session = session_factory()
        if state["armed"]:  # only the runner's first session fails to commit
            state["armed"] = False

            def boom():
                raise RuntimeError("db connection lost")

            session.commit = boom
        return session

    monkeypatch.setattr(jobs_module, "SessionLocal", flaky_session_factory)

    resp = client.post(
        "/api/scan/services/dds-api/rescan", json={"initiated_by": "tester"}
    )

    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    with session_factory() as s:
        job = s.get(RepositoryScanJob, job_id)
        assert job.status is JobStatus.failed
        assert job.error.startswith("could not start job:")
        assert job.finished_at is not None


def test_successful_scan_is_ingested_and_served_by_the_job_api(
    client, session_factory, monkeypatch
):
    """The full path with the real ingest: launch, scan, persist, poll. This is
    what the panel shows, so no part of it may be stubbed out."""
    _seed_service(session_factory, "ecs-api", name="ecs")

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                return RepositoryScanResult(
                    repository=IrService(repo=repo, documents=[make_endpoint()]),
                    branch=branch,
                    commit_hash="d" * 40,
                )

        return _Scanner()

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    # Ingest opens its own session, exactly like the runner does.
    monkeypatch.setattr(ingest_module, "SessionLocal", session_factory)
    monkeypatch.setattr(ingest_module, "get_engine", lambda: None)

    resp = client.post(
        "/api/scan/services/ecs-api/rescan", json={"initiated_by": "tester"}
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "done"
    assert body["error"] is None
    assert body["finished_at"] is not None
    assert body["commit_hash"] == "d" * 40
    assert body["scanner_version"] == SCANNER_VERSION

    with session_factory() as s:
        snapshot = s.scalars(select(Snapshot)).one()
        assert snapshot.source_job_id == job_id
        assert snapshot.documents_total == 1
        assert [record.kind for record in snapshot.documents] == ["endpoint"]


# --------------------------------------------------------------------------- #
# Termination (F17)
# --------------------------------------------------------------------------- #
def _seed_job(session_factory, service_id: int, status: JobStatus) -> int:
    """Insert one Job directly, honouring the status_timestamps constraint."""
    now = datetime.now(tz=UTC)
    with session_factory() as s:
        job = RepositoryScanJob(
            service_id=service_id,
            kind=JobKind.scan,
            status=status,
            initiated_by="tester",
            started_at=None if status is JobStatus.queued else now,
            finished_at=now if status in (JobStatus.done, JobStatus.failed) else None,
            error="boom" if status is JobStatus.failed else None,
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        return job.id


@pytest.mark.parametrize("status", [JobStatus.queued, JobStatus.running])
def test_cancel_moves_a_non_terminal_job_to_failed(client, session_factory, status):
    service_id = _seed_service(session_factory, f"cancel-{status.value}")
    job_id = _seed_job(session_factory, service_id, status)

    resp = client.post(f"/api/jobs/{job_id}/cancel")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"] == "cancelled by user"
    assert body["finished_at"] is not None

    with session_factory() as s:
        job = s.get(RepositoryScanJob, job_id)
        assert job.status is JobStatus.failed
        assert job.error == "cancelled by user"
        assert job.finished_at is not None


@pytest.mark.parametrize("status", [JobStatus.done, JobStatus.failed])
def test_cancel_conflicts_on_a_finished_job_and_leaves_it_untouched(
    client, session_factory, status
):
    service_id = _seed_service(session_factory, f"cancel-late-{status.value}")
    job_id = _seed_job(session_factory, service_id, status)
    with session_factory() as s:
        before = s.get(RepositoryScanJob, job_id)
        original = (before.status, before.error, before.finished_at)

    resp = client.post(f"/api/jobs/{job_id}/cancel")

    assert resp.status_code == 409
    assert status.value in resp.json()["error"]["message"]
    with session_factory() as s:
        job = s.get(RepositoryScanJob, job_id)
        assert (job.status, job.error, job.finished_at) == original


def test_cancel_unknown_job_returns_404(client):
    assert client.post("/api/jobs/9999/cancel").status_code == 404


def test_cancelling_unblocks_the_service_for_a_new_scan(
    client, session_factory, monkeypatch
):
    """The partial unique index allows one active scan job per service, so a
    stuck Job blocks the service until something closes it. That unblocking is
    the whole point of cancelling by ID."""
    service_id = _seed_service(session_factory, "stuck-api")
    _seed_job(session_factory, service_id, JobStatus.running)

    blocked = client.post(
        "/api/scan/services/stuck-api/rescan", json={"initiated_by": "tester"}
    )
    assert blocked.status_code == 409

    with session_factory() as s:
        stuck = s.scalars(
            select(RepositoryScanJob).where(RepositoryScanJob.service_id == service_id)
        ).one()
        stuck_id = stuck.id
    assert client.post(f"/api/jobs/{stuck_id}/cancel").status_code == 200

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                return RepositoryScanResult(
                    repository=IrService(repo=repo),
                    branch=branch,
                    commit_hash="f" * 40,
                )

        return _Scanner()

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(jobs_module, "ingest_service_result", lambda **kwargs: None)
    again = client.post(
        "/api/scan/services/stuck-api/rescan", json={"initiated_by": "tester"}
    )
    assert again.status_code == 202


def test_a_scan_cancelled_while_running_persists_nothing(
    client, session_factory, monkeypatch
):
    """The scan cannot be stopped, so it must not be allowed to land.

    BackgroundTasks gives no way to kill the worker thread, so termination is a
    database decision only: the scan runs to completion and the runner then
    finds the Job is no longer its own. If this regressed, a cancelled scan
    would quietly overwrite the cancellation with a snapshot and a `done` Job.
    """
    service_id = _seed_service(session_factory, "ecs-cancelled")

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                # The operator cancels while this scan is in flight.
                with session_factory() as s:
                    job = s.scalars(
                        select(RepositoryScanJob).where(
                            RepositoryScanJob.service_id == service_id
                        )
                    ).one()
                    job.status = JobStatus.failed
                    job.error = "cancelled by user"
                    job.finished_at = datetime.now(tz=UTC)
                    s.commit()
                return RepositoryScanResult(
                    repository=IrService(repo=repo),
                    branch=branch,
                    commit_hash="e" * 40,
                )

        return _Scanner()

    ingested = []
    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(
        jobs_module, "ingest_service_result", lambda **kw: ingested.append(kw)
    )

    resp = client.post(
        "/api/scan/services/ecs-cancelled/rescan", json={"initiated_by": "tester"}
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    assert ingested == []  # the result never reached ingest
    with session_factory() as s:
        assert s.scalars(select(Snapshot)).all() == []
        job = s.get(RepositoryScanJob, job_id)
        assert job.status is JobStatus.failed
        assert job.error == "cancelled by user"  # not overwritten


def test_a_failure_after_cancellation_keeps_the_cancellation_reason(
    client, session_factory, monkeypatch
):
    """Whoever stopped the Job stays on the record.

    A scan that fails after being cancelled must not replace "cancelled by user"
    with a provider error - that would erase the only evidence of why the Job
    stopped.
    """
    service_id = _seed_service(session_factory, "ecs-cancel-then-fail")

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                with session_factory() as s:
                    job = s.scalars(
                        select(RepositoryScanJob).where(
                            RepositoryScanJob.service_id == service_id
                        )
                    ).one()
                    job.status = JobStatus.failed
                    job.error = "cancelled by user"
                    job.finished_at = datetime.now(tz=UTC)
                    s.commit()
                raise RuntimeError("provider exploded")

        return _Scanner()

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)

    resp = client.post(
        "/api/scan/services/ecs-cancel-then-fail/rescan",
        json={"initiated_by": "tester"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    with session_factory() as s:
        assert s.get(RepositoryScanJob, job_id).error == "cancelled by user"


def test_a_job_cancelled_before_the_runner_starts_is_never_scanned(
    client, session_factory, monkeypatch
):
    service_id = _seed_service(session_factory, "ecs-cancel-early")
    job_id = _seed_job(session_factory, service_id, JobStatus.queued)
    scanned = []

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):  # pragma: no cover - must not run
                scanned.append(repo)
                raise AssertionError("a cancelled job must not be scanned")

        return _Scanner()

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    client.post(f"/api/jobs/{job_id}/cancel")

    jobs_module.run_scan_job(job_id)

    assert scanned == []
    with session_factory() as s:
        job = s.get(RepositoryScanJob, job_id)
        assert job.status is JobStatus.failed
        assert job.error == "cancelled by user"
        assert job.started_at is None  # never transitioned to running


# --------------------------------------------------------------------------- #
# Startup cleanup (F17)
# --------------------------------------------------------------------------- #
def test_startup_terminates_jobs_orphaned_by_a_restart(session_factory, monkeypatch):
    """Nothing resumes a Job across a restart, so leaving one non-terminal
    strands its service behind uq_active_scan_job_per_service forever."""
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    monkeypatch.setattr(jobs_module, "get_engine", lambda: None)

    queued_service = _seed_service(session_factory, "orphan-queued", name="q")
    running_service = _seed_service(session_factory, "orphan-running", name="r")
    done_service = _seed_service(session_factory, "orphan-done", name="d")
    queued = _seed_job(session_factory, queued_service, JobStatus.queued)
    running = _seed_job(session_factory, running_service, JobStatus.running)
    done = _seed_job(session_factory, done_service, JobStatus.done)

    terminated = jobs_module.terminate_orphaned_jobs()

    assert terminated == 2
    with session_factory() as s:
        for job_id in (queued, running):
            job = s.get(RepositoryScanJob, job_id)
            assert job.status is JobStatus.failed
            assert job.error == "interrupted by panel restart"
            assert job.finished_at is not None
        untouched = s.get(RepositoryScanJob, done)
        assert untouched.status is JobStatus.done
        assert untouched.error is None


def test_startup_cleanup_is_idempotent(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    monkeypatch.setattr(jobs_module, "get_engine", lambda: None)
    service_id = _seed_service(session_factory, "orphan-twice")
    _seed_job(session_factory, service_id, JobStatus.running)

    assert jobs_module.terminate_orphaned_jobs() == 1
    assert jobs_module.terminate_orphaned_jobs() == 0


def test_an_unreachable_database_degrades_startup_instead_of_stopping_it(monkeypatch):
    """The panel still serves every read endpoint without the cleanup, and the
    compose service has no restart policy - refusing to boot would take it down
    and leave it down over a janitorial step."""

    def unreachable() -> int:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(app_module, "terminate_orphaned_jobs", unreachable)

    with TestClient(app_module.create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert "rescan" in response.json()["detail"]


def test_health_is_ok_when_startup_cleanup_succeeded(monkeypatch):
    monkeypatch.setattr(app_module, "terminate_orphaned_jobs", lambda: 0)

    with TestClient(app_module.create_app()) as client:
        body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["detail"] is None


def test_a_defect_in_startup_cleanup_stops_the_panel_rather_than_no_opping(
    monkeypatch,
):
    """Only the operational failures are tolerated.

    A bug in our own cleanup would otherwise be swallowed on every boot, leaving
    orphaned jobs behind forever with one log line as the only evidence.
    """

    def broken() -> int:
        raise TypeError("cleanup is broken")

    monkeypatch.setattr(app_module, "terminate_orphaned_jobs", broken)

    with pytest.raises(TypeError), TestClient(app_module.create_app()):
        pass  # pragma: no cover - startup raises before the body runs


# --------------------------------------------------------------------------- #
# Exclusion (PS2-1)
# --------------------------------------------------------------------------- #
def _exclude(client, repo: str, reason: str = "deprecated upstream"):
    return client.post(
        f"/api/scan/services/{repo}/exclude",
        json={"reason": reason, "initiated_by": "operator"},
    )


def _exclusion_row(session_factory, service_id: int) -> ExcludedService | None:
    with session_factory() as s:
        return s.get(ExcludedService, service_id)


def test_exclude_records_who_asked_and_why(client, session_factory):
    service_id = _seed_service(session_factory, "dms-api")

    resp = _exclude(client, "dms-api", reason="retired by the service team")

    assert resp.status_code == 204
    assert resp.content == b""
    row = _exclusion_row(session_factory, service_id)
    assert row.reason == "retired by the service team"
    # Who asked comes from the token; the body's "operator" is ignored. The
    # column is excluded_by, and mapping the identity onto it is the endpoint's
    # job, so assert it here.
    assert row.excluded_by == TEST_WORKER.name
    assert row.excluded_at is not None


def test_exclude_leaves_jobs_and_snapshots_untouched(
    client, session_factory, monkeypatch
):
    """Exclusion hides a service; it never deletes what the service owns. If it
    did, restoring one would silently return an empty history."""
    _seed_service(session_factory, "css-api", name="css")

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                return RepositoryScanResult(
                    repository=IrService(repo=repo, documents=[make_endpoint()]),
                    branch=branch,
                    commit_hash="e" * 40,
                )

        return _Scanner()

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(ingest_module, "SessionLocal", session_factory)
    monkeypatch.setattr(ingest_module, "get_engine", lambda: None)
    client.post("/api/scan/services/css-api/rescan", json={"initiated_by": "tester"})

    assert _exclude(client, "css-api").status_code == 204

    with session_factory() as s:
        assert s.scalars(select(Snapshot)).one().documents_total == 1
        assert s.scalars(select(RepositoryScanJob)).one().status is JobStatus.done


def test_exclude_unknown_service_returns_404(client):
    resp = _exclude(client, "does-not-exist")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "body",
    [
        {"initiated_by": "operator"},
        {"reason": "", "initiated_by": "operator"},
        {"reason": "   ", "initiated_by": "operator"},
        {"reason": "deprecated", "initiated_by": ""},
    ],
    ids=["missing", "empty", "blank", "no-initiator"],
)
def test_exclude_requires_a_reason_and_an_initiator(client, session_factory, body):
    """The reason is the only record of why a service is hidden - `include`
    deletes the row rather than archiving it. Whitespace is refused too: stored
    as-is it would read as filled in on the excluded list."""
    _seed_service(session_factory, "swr-api")

    resp = client.post("/api/scan/services/swr-api/exclude", json=body)

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_excluding_an_already_excluded_service_conflicts(client, session_factory):
    _seed_service(session_factory, "rds-api")
    assert _exclude(client, "rds-api").status_code == 204

    resp = _exclude(client, "rds-api", reason="second thoughts")

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
    assert "rds-api" in resp.json()["error"]["message"]


def test_exclude_and_include_resolve_a_repo_containing_slashes(client, session_factory):
    """The URL segment carries ``Service.repo``, which contains a ``/``; seeded
    with repo != name so a name-based lookup cannot pass by accident."""
    repo = "opentelekomcloud-docs/vpc-api"
    service_id = _seed_service(session_factory, repo, name="vpc-api")

    assert _exclude(client, repo).status_code == 204
    assert _exclusion_row(session_factory, service_id) is not None

    assert client.post(f"/api/scan/services/{repo}/include").status_code == 204
    assert _exclusion_row(session_factory, service_id) is None


def test_include_removes_the_exclusion_without_an_audit_trail(client, session_factory):
    """Restoring deletes the row outright - there is no archived copy, so the
    reason text lives exactly as long as the exclusion does."""
    service_id = _seed_service(session_factory, "dcs-api")
    assert _exclude(client, "dcs-api").status_code == 204

    resp = client.post("/api/scan/services/dcs-api/include")

    assert resp.status_code == 204
    assert resp.content == b""
    assert _exclusion_row(session_factory, service_id) is None


def test_include_unknown_service_returns_404(client):
    resp = client.post("/api/scan/services/does-not-exist/include")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_including_a_service_that_is_not_excluded_conflicts(client, session_factory):
    """A no-op 204 would tell the operator their restore worked when there was
    nothing to restore."""
    _seed_service(session_factory, "waf-api")

    resp = client.post("/api/scan/services/waf-api/include")

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
    assert "waf-api" in resp.json()["error"]["message"]


def test_rescanning_an_excluded_service_conflicts(client, session_factory):
    _seed_service(session_factory, "sfs-api")
    assert _exclude(client, "sfs-api").status_code == 204

    resp = client.post(
        "/api/scan/services/sfs-api/rescan", json={"initiated_by": "tester"}
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
    with session_factory() as s:
        assert s.scalars(select(RepositoryScanJob)).all() == []


def test_rescan_is_allowed_again_once_the_service_is_included(
    client, session_factory, monkeypatch
):
    _seed_service(session_factory, "as-api")
    assert _exclude(client, "as-api").status_code == 204
    assert client.post("/api/scan/services/as-api/include").status_code == 204

    monkeypatch.setattr(jobs_module, "run_scan_job", lambda _job_id: None)
    resp = client.post(
        "/api/scan/services/as-api/rescan", json={"initiated_by": "tester"}
    )

    assert resp.status_code == 202


def test_an_unchanged_rescan_still_reports_the_commit_it_read(
    client, session_factory, monkeypatch
):
    """The Job API reads scanner_version and commit_hash from the Job's result
    Snapshot, not from one it created. A rescan that finds nothing changed
    creates no Snapshot, and sourcing these from the created one would blank
    them out - the UI would show a finished scan that read nothing."""
    _seed_service(session_factory, "steady-api", name="steady")

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                return RepositoryScanResult(
                    repository=IrService(repo=repo, documents=[make_endpoint()]),
                    branch=branch,
                    commit_hash="c" * 40,
                )

        return _Scanner()

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(ingest_module, "SessionLocal", session_factory)
    monkeypatch.setattr(ingest_module, "get_engine", lambda: None)

    first = client.post(
        "/api/scan/services/steady-api/rescan", json={"initiated_by": "tester"}
    ).json()["job_id"]
    second = client.post(
        "/api/scan/services/steady-api/rescan", json={"initiated_by": "tester"}
    ).json()["job_id"]

    assert second != first
    body = client.get(f"/api/jobs/{second}").json()
    assert body["status"] == "done"
    assert body["commit_hash"] == "c" * 40
    assert body["scanner_version"] == SCANNER_VERSION
    with session_factory() as s:
        # The second scan changed nothing, so it stored no second Snapshot.
        assert len(s.scalars(select(Snapshot)).all()) == 1


def _set_eligibility(session_factory, repo: str, has_api_ref: bool | None) -> None:
    with session_factory() as s:
        service = s.scalar(select(Service).where(Service.repo == repo))
        service.has_api_ref = has_api_ref
        s.commit()


@pytest.mark.parametrize("action", ["rescan", "exclude"])
def test_an_ineligible_service_can_be_neither_scanned_nor_excluded(
    client, session_factory, action
):
    """There is nothing to scan, so a scan would fail on the first lookup; and
    excluding one is meaningless, because it is already out of every list the
    exclusion would remove it from."""
    _seed_service(session_factory, "no-docs-api")
    _set_eligibility(session_factory, "no-docs-api", False)

    resp = client.post(
        f"/api/scan/services/no-docs-api/{action}",
        json={"initiated_by": "tester", "reason": "retired"},
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
    assert "no-docs-api" in resp.json()["error"]["message"]
    with session_factory() as s:
        assert s.scalars(select(RepositoryScanJob)).all() == []
        assert s.scalars(select(ExcludedService)).all() == []


@pytest.mark.parametrize("action", ["rescan", "exclude"])
def test_a_service_never_checked_for_eligibility_stays_usable(
    client, session_factory, monkeypatch, action
):
    """NULL means discovery has never looked at this repository - every
    hand-registered service starts there. Treating it as ineligible would lock
    the panel's own `register-service` command out of its own endpoints."""
    _seed_service(session_factory, "unchecked-api")
    with session_factory() as s:
        assert s.scalars(select(Service)).one().has_api_ref is None
    monkeypatch.setattr(jobs_module, "run_scan_job", lambda _job_id: None)

    resp = client.post(
        f"/api/scan/services/unchecked-api/{action}",
        json={"initiated_by": "tester", "reason": "retired"},
    )

    assert resp.status_code == (202 if action == "rescan" else 204)


def test_exclusion_and_scan_launch_serialize_on_the_service_row(session_factory):
    """The exclusion guard in ``start_scan`` is only worth the lock under it.

    Without ``with_for_update`` an exclude and a launch could both read "not
    excluded yet" and both commit, leaving a scan running against a service the
    operator had just hidden - and no unique index would catch it, because the
    two writes touch different tables. Proven by asking for the same row from a
    second transaction with ``NOWAIT``: it is refused, so the row is genuinely
    held rather than merely read.
    """
    _seed_service(session_factory, "lock-api")

    with session_factory() as holder:
        scans_module._locked_service_or_404(holder, "lock-api")

        with session_factory() as other, pytest.raises(OperationalError):
            other.scalar(
                select(Service)
                .where(Service.repo == "lock-api")
                .with_for_update(nowait=True)
            )


def test_a_scan_already_running_when_exclusion_lands_still_ingests(
    client, session_factory, monkeypatch
):
    """The documented edge case: exclusion takes effect from the next launch,
    not retroactively. Killing an in-flight scan would either throw away work
    that already cost its rate-limit budget or persist half a snapshot, so the
    job runs to completion and its data lands."""
    service_id = _seed_service(session_factory, "obs-api", name="obs")

    def fake_build_scanner(_settings):
        class _Scanner:
            def scan_repository(self, repo, branch):
                # The operator excludes the service while this scan is in flight.
                with session_factory() as s:
                    s.add(
                        ExcludedService(
                            service_id=service_id,
                            reason="retired mid-scan",
                            excluded_by="operator",
                        )
                    )
                    s.commit()
                return RepositoryScanResult(
                    repository=IrService(repo=repo, documents=[make_endpoint()]),
                    branch=branch,
                    commit_hash="f" * 40,
                )

        return _Scanner()

    monkeypatch.setattr(jobs_module, "build_scanner", fake_build_scanner)
    monkeypatch.setattr(ingest_module, "SessionLocal", session_factory)
    monkeypatch.setattr(ingest_module, "get_engine", lambda: None)

    resp = client.post(
        "/api/scan/services/obs-api/rescan", json={"initiated_by": "tester"}
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "done"
    assert body["error"] is None
    with session_factory() as s:
        snapshot = s.scalars(select(Snapshot)).one()
        assert snapshot.source_job_id == job_id
        assert snapshot.documents_total == 1
