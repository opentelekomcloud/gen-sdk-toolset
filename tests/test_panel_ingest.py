"""Ingest of a successful repository scan into the existing Job (issue #16).

Reuses the PostgreSQL provisioning from tests/test_panel_db.py, so this module
is skipped unless TEST_DATABASE_URL is set or Docker is available (see that
module's docstring).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from tests.test_panel_db import (  # noqa: E402,F401  (reused DB fixtures)
    _alembic_config,
    admin_url,
    make_endpoint,
    make_plain_document,
    scratch_database,
)
from tools.panel.core import ingest as ingest_module  # noqa: E402
from tools.panel.core.db.models import (  # noqa: E402
    DocumentRecord,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
    Snapshot,
)
from tools.panel.core.ingest import IngestRejected, ingest_service_result  # noqa: E402
from tools.shared.ir import (  # noqa: E402
    DOCUMENT_SCHEMA_VERSION,
    Document,
    Endpoint,
    Repository,  # noqa: E402
)
from tools.shared.ir import Service as IrService  # noqa: E402
from tools.shared.scan import (  # noqa: E402
    RepositoryInterruption,
    RepositoryInterruptionKind,
    RepositoryScanResult,
)

REPO = "opentelekomcloud-docs/ecs"
COMMIT = "a" * 40
# The status_timestamps CHECK constraint: only queued has no started_at, and
# only the terminal states carry finished_at.
_TERMINAL = (JobStatus.done, JobStatus.failed)


def _now() -> datetime:
    return datetime.now(tz=UTC)


@pytest.fixture
def engine(scratch_database):  # noqa: F811  (pytest fixture injection)
    url = scratch_database("panel_test_ingest")
    command.upgrade(_alembic_config(url), "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def bound_ingest(session_factory, monkeypatch):
    """Point ingest's own session factory at the scratch database."""
    monkeypatch.setattr(ingest_module, "SessionLocal", session_factory)
    monkeypatch.setattr(ingest_module, "get_engine", lambda: None)


def _seed_running_job(
    session_factory,
    *,
    repo: str = REPO,
    status: JobStatus = JobStatus.running,
    kind: JobKind = JobKind.scan,
) -> tuple[int, int]:
    """Insert a Service and one Job in the given state; return their ids."""
    with session_factory() as session:
        service = Service(repo=repo, name=repo.split("/")[-1], branch="main")
        session.add(service)
        session.flush()
        job = RepositoryScanJob(
            service_id=service.id,
            kind=kind,
            status=status,
            initiated_by="tester",
            started_at=None if status is JobStatus.queued else _now(),
            finished_at=_now() if status in _TERMINAL else None,
            error="earlier failure" if status is JobStatus.failed else None,
        )
        session.add(job)
        session.commit()
        return service.id, job.id


def _result(
    *,
    repo: str = REPO,
    documents: list[Document] | None = None,
    commit_hash: str | None = COMMIT,
    excluded: list[str] | None = None,
) -> RepositoryScanResult:
    return RepositoryScanResult(
        repository=IrService(
            repo=repo,
            documents=_documents() if documents is None else documents,
        ),
        branch="main",
        commit_hash=commit_hash,
        excluded_documents=(
            ["api-ref/source/out-of-date_apis/old.rst"]
            if excluded is None
            else excluded
        ),
    )


def _documents() -> list[Document]:
    """One partial endpoint (2 fields, 1 recognized) and one unsupported page."""
    return [make_endpoint(), make_plain_document()]


def _ingest(job_id: int, result: RepositoryScanResult, repo: str = REPO) -> None:
    ingest_service_result(job_id=job_id, service_repo=repo, result=result)


# ---------------------------------------------------------------------------
# Successful ingest
# ---------------------------------------------------------------------------


def test_successful_ingest_persists_snapshot_and_completes_job(session_factory):
    service_id, job_id = _seed_running_job(session_factory)

    _ingest(job_id, _result())

    with session_factory() as session:
        snapshot = session.scalars(select(Snapshot)).one()
        job = session.get(RepositoryScanJob, job_id)

        assert snapshot.service_id == service_id
        assert snapshot.source_job_id == job_id
        assert snapshot.branch == "main"
        assert snapshot.commit_hash == COMMIT
        assert (
            snapshot.scanner_version
            == RepositoryScanResult(
                repository=IrService(repo=REPO), branch="main"
            ).scanner_version
        )
        assert snapshot.document_schema_version == DOCUMENT_SCHEMA_VERSION
        assert snapshot.excluded_documents == [
            "api-ref/source/out-of-date_apis/old.rst"
        ]

        assert snapshot.documents_total == 2
        assert snapshot.endpoints_total == 1
        assert snapshot.non_endpoint_documents == 1
        assert snapshot.partial_count == 1
        assert snapshot.unsupported_count == 1
        assert snapshot.ok_count == snapshot.failed_count == 0
        assert snapshot.issues_total == 2
        assert snapshot.completeness == 0.5

        assert job.status is JobStatus.done
        assert job.error is None
        assert job.finished_at is not None
        # One event, one timestamp: the UI reads created_at as the scan time.
        assert snapshot.created_at == job.finished_at


def test_documents_persist_with_their_kind_and_payload(session_factory):
    _, job_id = _seed_running_job(session_factory)

    _ingest(job_id, _result())

    with session_factory() as session:
        records = session.scalars(
            select(DocumentRecord).order_by(DocumentRecord.kind)
        ).all()
        by_kind = {record.kind: record for record in records}

        assert set(by_kind) == {"document", "endpoint"}

        endpoint_record = by_kind["endpoint"]
        endpoint = Endpoint.model_validate(endpoint_record.payload)
        assert endpoint == make_endpoint()  # lossless round trip
        assert endpoint_record.path == endpoint.path
        assert endpoint_record.method == endpoint.method.value
        assert endpoint_record.uri == endpoint.uri
        assert endpoint_record.api_version == endpoint.api_version
        assert endpoint_record.overall_status == "partial"
        assert endpoint_record.completeness == 0.5
        assert endpoint_record.issues_count == 1

        plain_record = by_kind["document"]
        assert Document.model_validate(plain_record.payload) == make_plain_document()
        assert plain_record.method is None and plain_record.uri is None
        assert plain_record.overall_status == "unsupported"
        # Unmeasurable, not zero.
        assert plain_record.completeness is None
        assert plain_record.issues_count == 1


def test_analytics_payload_accounts_for_every_document(session_factory):
    _, job_id = _seed_running_job(session_factory)

    _ingest(job_id, _result())

    with session_factory() as session:
        analytics = session.scalars(select(Snapshot)).one().analytics

    assert analytics["documents_total"] == 2
    assert (
        analytics["ok_count"]
        + analytics["partial_count"]
        + analytics["failed_count"]
        + analytics["unsupported_count"]
        + analytics["unknown_count"]
        == analytics["documents_total"]
    )
    assert analytics["issues_by_code"] == {
        "unknown_type_format": 1,
        "unsupported_doc_style": 1,
    }
    assert analytics["by_section_status"]["body"] == {"partial": 1}
    assert analytics["by_version"] == {"v1": 1}
    assert analytics["fields_total"] == 2
    assert analytics["fields_recognized"] == 1


def test_service_scan_metadata_is_updated(session_factory):
    service_id, job_id = _seed_running_job(session_factory)

    _ingest(job_id, _result())

    with session_factory() as session:
        service = session.get(Service, service_id)
        snapshot = session.scalars(select(Snapshot)).one()

        assert service.has_api_ref is True
        assert service.eligibility_checked_at == snapshot.created_at
        assert service.latest_snapshot_id == snapshot.id
        assert service.active_snapshot_id == snapshot.id
        # Discovery owns head_commit — the branch HEAD, which is not the
        # commit this scan read; ingest leaves it alone.
        assert service.head_commit is None


def test_ingest_does_not_create_a_second_job(session_factory):
    service_id, job_id = _seed_running_job(session_factory)

    _ingest(job_id, _result())

    with session_factory() as session:
        jobs = session.scalars(
            select(RepositoryScanJob).where(RepositoryScanJob.service_id == service_id)
        ).all()
        assert [job.id for job in jobs] == [job_id]
        assert session.scalars(select(Snapshot)).one().source_job_id == job_id


def test_scan_without_documents_persists_an_empty_snapshot(session_factory):
    """An eligible repository with no API-reference documents is a successful
    scan, not a failure - it must still produce a Snapshot."""
    _, job_id = _seed_running_job(session_factory)

    _ingest(job_id, _result(documents=[], excluded=[]))

    with session_factory() as session:
        snapshot = session.scalars(select(Snapshot)).one()
        assert snapshot.documents_total == 0
        assert snapshot.completeness is None
        assert session.get(RepositoryScanJob, job_id).status is JobStatus.done


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------


def _assert_nothing_persisted(
    session_factory,
    job_id: int | None,
    *,
    job_status: JobStatus | None = JobStatus.running,
) -> None:
    """No Snapshot, no documents, and the Job left exactly as it was found."""
    with session_factory() as session:
        assert session.scalars(select(Snapshot)).all() == []
        assert session.scalars(select(DocumentRecord)).all() == []
        if job_id is not None:
            job = session.get(RepositoryScanJob, job_id)
            assert job.status is job_status
            service = session.get(Service, job.service_id)
            assert service.active_snapshot_id is None
            assert service.latest_snapshot_id is None


def test_rejects_unknown_job(session_factory):
    with pytest.raises(IngestRejected, match="does not exist"):
        _ingest(999999, _result())

    _assert_nothing_persisted(session_factory, None)


@pytest.mark.parametrize("status", [JobStatus.queued, JobStatus.done, JobStatus.failed])
def test_rejects_job_that_is_not_running(session_factory, status):
    _, job_id = _seed_running_job(session_factory, status=status)

    with pytest.raises(IngestRejected, match="expected running"):
        _ingest(job_id, _result())

    _assert_nothing_persisted(session_factory, job_id, job_status=status)


def test_rejects_job_of_another_kind(session_factory):
    _, job_id = _seed_running_job(session_factory, kind=JobKind.generate)

    with pytest.raises(IngestRejected, match="expected scan"):
        _ingest(job_id, _result())

    _assert_nothing_persisted(session_factory, job_id)


def test_rejects_failed_scan_result(session_factory):
    _, job_id = _seed_running_job(session_factory)
    result = RepositoryScanResult(
        repository=IrService(repo=REPO),
        branch="main",
        commit_hash=COMMIT,
        error="file tree truncated by provider",
    )

    with pytest.raises(IngestRejected, match="truncated"):
        _ingest(job_id, result)

    _assert_nothing_persisted(session_factory, job_id)


def test_rejects_interrupted_scan_result(session_factory):
    _, job_id = _seed_running_job(session_factory)
    result = RepositoryScanResult(
        repository=IrService(repo=REPO),
        branch="main",
        commit_hash=COMMIT,
        interruption=RepositoryInterruption(
            kind=RepositoryInterruptionKind.rate_limit,
            repository=REPO,
            message="rate limit exceeded",
        ),
    )

    with pytest.raises(IngestRejected, match="rate limit exceeded"):
        _ingest(job_id, result)

    _assert_nothing_persisted(session_factory, job_id)


def test_rejects_result_without_resolved_commit(session_factory):
    _, job_id = _seed_running_job(session_factory)

    with pytest.raises(IngestRejected, match="no resolved commit hash"):
        _ingest(job_id, _result(commit_hash=None))

    _assert_nothing_persisted(session_factory, job_id)


def test_rejects_repository_that_is_not_a_service(session_factory):
    _, job_id = _seed_running_job(session_factory)
    result = RepositoryScanResult(
        repository=Repository(repo=REPO), branch="main", commit_hash=COMMIT
    )

    with pytest.raises(IngestRejected, match="not a Service"):
        _ingest(job_id, result)

    _assert_nothing_persisted(session_factory, job_id)


def test_rejects_result_scanned_from_another_repository(session_factory):
    _, job_id = _seed_running_job(session_factory)

    with pytest.raises(IngestRejected, match="repository mismatch"):
        _ingest(job_id, _result(repo="opentelekomcloud-docs/vpc"))

    _assert_nothing_persisted(session_factory, job_id)


def test_rejects_request_for_another_service(session_factory):
    """The Job's Service, the requested repo and the scanned repo must agree."""
    _, job_id = _seed_running_job(session_factory)
    other = "opentelekomcloud-docs/vpc"

    with pytest.raises(IngestRejected, match="repository mismatch"):
        ingest_service_result(
            job_id=job_id, service_repo=other, result=_result(repo=other)
        )

    _assert_nothing_persisted(session_factory, job_id)


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


def test_failure_after_the_snapshot_insert_leaves_nothing_behind(
    session_factory, monkeypatch
):
    """The Snapshot is already flushed when the documents are built - a
    failure there must roll it back, not leave an empty snapshot visible."""
    _, job_id = _seed_running_job(session_factory)

    def boom(_document):
        raise RuntimeError("analytics exploded")

    monkeypatch.setattr(ingest_module, "analyze_document", boom)

    with pytest.raises(RuntimeError, match="analytics exploded"):
        _ingest(job_id, _result())

    _assert_nothing_persisted(session_factory, job_id)
    with session_factory() as session:
        assert session.get(RepositoryScanJob, job_id).status is JobStatus.running


def test_second_ingest_of_the_same_job_is_rejected(session_factory):
    _, job_id = _seed_running_job(session_factory)

    _ingest(job_id, _result())
    with pytest.raises(IngestRejected, match="expected running"):
        _ingest(job_id, _result())

    with session_factory() as session:
        assert len(session.scalars(select(Snapshot)).all()) == 1
