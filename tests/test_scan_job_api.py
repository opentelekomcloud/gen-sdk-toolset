"""API tests for scan launch and job polling (F7 happy path).

Reuses the PostgreSQL provisioning from tests/test_panel_db.py, so this module
is skipped unless TEST_DATABASE_URL is set or Docker is available (see that
module's docstring).
"""

from __future__ import annotations

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
    scratch_database,
)
from tools.panel.api import deps  # noqa: E402
from tools.panel.api.app import create_app  # noqa: E402
from tools.panel.core import jobs as jobs_module  # noqa: E402
from tools.panel.core.db.models import (  # noqa: E402
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
)
from tools.shared.ir import Service as IrService  # noqa: E402
from tools.shared.scan import RepositoryScanResult  # noqa: E402


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
        assert job.initiated_by == "tester"


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
    assert body["scanner_version"] is None  # no generation until ingest
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
        s.add(
            RepositoryScanJob(
                service_id=service_id,
                kind=JobKind.scan,
                status=JobStatus.queued,
                initiated_by="someone",
            )
        )
        s.commit()

    resp = client.post(
        "/api/scan/services/vpc-api/rescan", json={"initiated_by": "tester"}
    )

    assert resp.status_code == 409
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
