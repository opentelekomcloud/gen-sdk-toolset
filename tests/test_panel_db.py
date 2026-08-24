"""PostgreSQL-backed tests for the panel persistence layer.

Database resolution order:

1. ``TEST_DATABASE_URL`` environment variable (an admin PostgreSQL URL whose
   role may create/drop scratch databases), e.g.
   ``postgresql+psycopg://panel:panel@localhost:5432/panel``;
2. otherwise a throwaway ``postgres:16-alpine`` container via testcontainers
   (requires a Docker daemon).

Without either, the module is skipped.

Both paths pin ``sslmode=disable`` unless the URL already sets it: a test
container speaks no TLS, and libpq would otherwise honour a ``PGSSLMODE`` left
in the environment for some unrelated database.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from tools.panel.core.db.models import (  # noqa: E402
    DocumentRecord,
    ExcludedService,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
    Snapshot,
)
from tools.shared.ir import (  # noqa: E402
    DOCUMENT_SCHEMA_VERSION,
    Document,
    Endpoint,
    Example,
    HttpMethod,
    Parameter,
    ParameterType,
    Section,
    SectionName,
)
from tools.shared.scan import (  # noqa: E402
    DocumentScanResult,
    Issue,
    IssueCode,
    SectionScanResult,
    SectionStatus,
)

REPO_ROOT = Path(__file__).parent.parent
MIGRATIONS = REPO_ROOT / "src" / "tools" / "panel" / "core" / "db" / "migrations"


# ---------------------------------------------------------------------------
# Database provisioning
# ---------------------------------------------------------------------------


def _without_tls(url: str) -> str:
    """Pin ``sslmode=disable`` unless the URL already says otherwise.

    libpq reads ``PGSSLMODE`` from the environment, so a developer who has it
    set to ``require`` or ``verify-full`` for some other database cannot connect
    to a local test container at all - it offers no TLS. Without this the suite
    passes for whoever happens not to have the variable set and fails for
    everyone else, which is the worst kind of test failure.
    """
    if "sslmode=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}sslmode=disable"


@pytest.fixture(scope="session")
def admin_url() -> str:
    """Admin PostgreSQL URL used to create scratch databases."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield _without_tls(url)
        return

    docker = pytest.importorskip(
        "testcontainers.postgres",
        reason="TEST_DATABASE_URL is not set and testcontainers is unavailable",
    )
    try:
        container = docker.PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except Exception as error:  # docker daemon missing, or the container failed
        pytest.skip(
            f"TEST_DATABASE_URL is not set and no test container could start: {error}"
        )
    yield _without_tls(container.get_connection_url())
    container.stop()


@pytest.fixture(scope="session")
def scratch_database(admin_url):
    """Create a uniquely-named scratch database and return its URL."""
    created: list[str] = []

    def factory(name: str) -> str:
        assert name.isidentifier(), f"unsafe database name: {name!r}"
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as connection:
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
            connection.execute(sa.text(f'CREATE DATABASE "{name}"'))
        admin_engine.dispose()
        created.append(name)
        return (
            sa.engine.make_url(admin_url)
            .set(database=name)
            .render_as_string(hide_password=False)
        )

    yield factory

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        for name in created:
            connection.execute(
                sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            )
    admin_engine.dispose()


def _alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    # configparser interpolation: literal % must be doubled (e.g. %2F in URLs).
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def migrated_engine(scratch_database):
    """Engine bound to a scratch database migrated to head."""
    url = scratch_database("panel_test_models")
    command.upgrade(_alembic_config(url), "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine):
    """Transaction-per-test session; everything rolls back afterwards."""
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Canonical fixtures
# ---------------------------------------------------------------------------


def make_endpoint() -> Endpoint:
    """A canonical endpoint exercising parameters, examples, and issues."""
    sections = []
    for name in SectionName:
        if name is SectionName.BODY:
            sections.append(
                Section(
                    name=name,
                    parameters=[
                        Parameter(
                            name="server",
                            param_type=ParameterType.OBJECT,
                            mandatory=True,
                            description="Server spec.",
                            children=[
                                Parameter(
                                    name="flavor",
                                    param_type=ParameterType.STRING,
                                    type_name="String",
                                )
                            ],
                        )
                    ],
                    scan_result=SectionScanResult(
                        status=SectionStatus.PARTIAL,
                        issues=[
                            Issue(
                                code=IssueCode.UNKNOWN_TYPE_FORMAT,
                                location="server.flavor",
                                details="unrecognised type",
                            )
                        ],
                        fields_total=2,
                        fields_recognized=1,
                        fields_unknown_type=1,
                    ),
                )
            )
        elif name is SectionName.EXAMPLE_REQUEST:
            sections.append(
                Section(
                    name=name,
                    examples=[
                        Example(
                            raw='{"server": {"flavor": "s3.large"}}',
                            language="json",
                            parsed={"server": {"flavor": "s3.large"}},
                            label="Creating a server",
                        )
                    ],
                    scan_result=SectionScanResult(status=SectionStatus.OK),
                )
            )
        else:
            sections.append(
                Section(
                    name=name,
                    scan_result=SectionScanResult(status=SectionStatus.MISSING),
                )
            )
    return Endpoint(
        path="api-ref/source/create_server.rst",
        title="Creating a Server",
        method=HttpMethod.POST,
        uri="/v1/{project_id}/servers",
        api_version="v1",
        sections=sections,
        scan_result=DocumentScanResult(),
    )


def make_plain_document() -> Document:
    return Document(
        path="api-ref/source/history.rst",
        title="Change History",
        scan_result=DocumentScanResult(
            failure_reason=Issue(
                code=IssueCode.UNSUPPORTED_DOC_STYLE,
                details="not an endpoint document",
            )
        ),
    )


def make_snapshot(session: Session, repo: str = "opentelekomcloud-docs/ecs"):
    service = Service(repo=repo, name=repo.split("/")[-1], branch="main")
    session.add(service)
    session.flush()
    job = RepositoryScanJob(
        service_id=service.id,
        kind=JobKind.scan,
        status=JobStatus.done,
        started_at=sa.func.now(),
        finished_at=sa.func.now(),
    )
    session.add(job)
    session.flush()
    snapshot = Snapshot(
        service_id=service.id,
        source_job_id=job.id,
        branch="main",
        commit_hash="a" * 40,
        scanner_version="0.1.0",
        document_schema_version=DOCUMENT_SCHEMA_VERSION,
        analytics={},
    )
    session.add(snapshot)
    session.flush()
    return service, job, snapshot


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


def test_migration_upgrade_creates_schema_and_downgrade_removes_it(scratch_database):
    url = scratch_database("panel_test_migrations")
    config = _alembic_config(url)
    engine = create_engine(url)

    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert {"service", "excluded_service", "job", "snapshot", "document"} <= set(
        inspector.get_table_names()
    )
    service_fks = {fk["name"] for fk in inspector.get_foreign_keys("service")}
    assert {"fk_service_active_snapshot", "fk_service_latest_snapshot"} <= (service_fks)
    document_columns = {column["name"] for column in inspector.get_columns("document")}
    assert {"payload", "kind", "path", "method", "uri", "completeness"} <= (
        document_columns
    )

    command.downgrade(config, "base")
    inspector = inspect(engine)
    assert not {"service", "excluded_service", "job", "snapshot", "document"} & set(
        inspector.get_table_names()
    )
    engine.dispose()


#: Every database object the generation -> snapshot rename had to touch. Kept as
#: a literal list because the point of the assertion is that nothing was missed:
#: deriving it from the models would ask the same source that could be wrong.
_RENAMED_OBJECTS = """
    SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE :like
    UNION ALL
    SELECT table_name || '.' || column_name FROM information_schema.columns
        WHERE table_schema='public' AND column_name LIKE :like
    UNION ALL
    SELECT conname FROM pg_constraint
        WHERE connamespace='public'::regnamespace AND conname LIKE :like
    UNION ALL
    SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname LIKE :like
    UNION ALL
    SELECT sequencename FROM pg_sequences
        WHERE schemaname='public' AND sequencename LIKE :like
"""


def _objects_named(connection, word: str) -> set[str]:
    rows = connection.execute(sa.text(_RENAMED_OBJECTS), {"like": f"%{word}%"})
    return {row[0] for row in rows}


def test_generation_to_snapshot_rename_preserves_data_and_leaves_no_old_names(
    scratch_database,
):
    """The rename must carry existing scan results across, both ways.

    A rename migration is the one kind that can destroy data while looking
    correct: had it been autogenerated, Alembic would have emitted a DROP and a
    CREATE, and every persisted scan result would be gone with a green run. So
    this seeds the pre-rename schema, upgrades, and checks the rows and the
    active/latest pointers by value - not just that the tables exist.
    """
    url = scratch_database("panel_test_rename")
    config = _alembic_config(url)
    engine = create_engine(url)
    rename = "3dc12466f2fd"

    command.upgrade(config, f"{rename}-1")
    with engine.begin() as connection:
        connection.execute(
            sa.text("""
            INSERT INTO service (repo, name, branch, has_api_ref)
                VALUES ('opentelekomcloud-docs/ecs', 'ecs', 'main', true);
            INSERT INTO job (service_id, kind, status, started_at, finished_at)
                SELECT id, 'scan', 'done', now(), now() FROM service;
            INSERT INTO generation (service_id, source_job_id, branch, commit_hash,
                    scanner_version, document_schema_version, analytics)
                SELECT s.id, j.id, 'main', repeat('a', 40), '0.1.0', '1',
                    '{"ok_count": 1}'::jsonb
                FROM service s JOIN job j ON j.service_id = s.id;
            INSERT INTO document (generation_id, payload, overall_status)
                SELECT g.id,
                    '{"kind": "endpoint", "path": "api-ref/source/a.rst"}'::jsonb, 'ok'
                FROM generation g;
            UPDATE service SET active_generation_id = (SELECT id FROM generation),
                latest_generation_id = (SELECT id FROM generation);
            """)
        )
        before = connection.execute(
            sa.text("""
            SELECT g.id, g.commit_hash, g.analytics, s.active_generation_id,
                s.latest_generation_id
            FROM generation g JOIN service s ON s.id = g.service_id
            """)
        ).one()

    command.upgrade(config, rename)
    with engine.begin() as connection:
        after = connection.execute(
            sa.text("""
            SELECT p.id, p.commit_hash, p.analytics, s.active_snapshot_id,
                s.latest_snapshot_id
            FROM snapshot p JOIN service s ON s.id = p.service_id
            """)
        ).one()
        assert after == before
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM document WHERE snapshot_id = :id"),
                {"id": after[0]},
            ).scalar_one()
            == 1
        )
        # The sequence is renamed too, so it must still issue ids afterwards.
        assert _objects_named(connection, "generation") == set()
        assert "snapshot_id_seq" in _objects_named(connection, "snapshot")

    command.downgrade(config, f"{rename}-1")
    with engine.begin() as connection:
        restored = connection.execute(
            sa.text("""
            SELECT g.id, g.commit_hash, g.analytics, s.active_generation_id,
                s.latest_generation_id
            FROM generation g JOIN service s ON s.id = g.service_id
            """)
        ).one()
        assert restored == before
        assert _objects_named(connection, "snapshot") == set()
    engine.dispose()


def test_has_api_ref_backfill_separates_unchecked_from_ineligible(scratch_database):
    """Before this revision, false meant both "checked, no API reference" and
    "never checked" - the column had a NOT NULL default nobody set explicitly.
    The backfill has to recover the difference, and the only evidence of it is
    ``eligibility_checked_at``: a row with no timestamp was never checked, so
    its false was a placeholder rather than a finding.

    The dropped DEFAULT is asserted too. Autogenerate kept it, and left in
    place it would put every future row straight into "checked and ineligible"
    - a claim discovery never made, and one that would hide the row from the
    registry.
    """
    url = scratch_database("panel_test_has_api_ref")
    config = _alembic_config(url)
    engine = create_engine(url)
    revision = "3c0847043ef9"

    command.upgrade(config, f"{revision}-1")
    with engine.begin() as connection:
        connection.execute(
            sa.text("""
            INSERT INTO service (repo, name, branch, has_api_ref,
                    eligibility_checked_at)
                VALUES ('org/checked-eligible', 'a', 'main', true, now()),
                    ('org/checked-ineligible', 'b', 'main', false, now()),
                    ('org/never-checked', 'c', 'main', false, NULL),
                    ('org/never-checked-true', 'd', 'main', true, NULL);
            """)
        )

    command.upgrade(config, revision)
    with engine.begin() as connection:
        assert dict(
            connection.execute(
                sa.text("SELECT repo, has_api_ref FROM service ORDER BY repo")
            ).all()
        ) == {
            "org/checked-eligible": True,
            "org/checked-ineligible": False,
            # No timestamp means the check never ran, whatever the column said.
            "org/never-checked": None,
            "org/never-checked-true": None,
        }
        connection.execute(
            sa.text(
                "INSERT INTO service (repo, name, branch) "
                "VALUES ('org/fresh', 'e', 'main')"
            )
        )
        assert (
            connection.execute(
                sa.text("SELECT has_api_ref FROM service WHERE repo = 'org/fresh'")
            ).scalar_one()
            is None
        )

    # Downgrading re-collapses the two meanings, which is lossy by nature; what
    # it may not do is fail against rows the new state allows.
    command.downgrade(config, f"{revision}-1")
    with engine.begin() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM service WHERE has_api_ref IS NULL")
            ).scalar_one()
            == 0
        )
    engine.dispose()


def test_result_snapshot_backfill_links_every_job_that_produced_one(scratch_database):
    """Before this revision the link existed only as ``snapshot.source_job_id``,
    and every successful Job had its own Snapshot - so that column is a complete
    source for the backfill. A Job that never produced a result keeps NULL,
    which is what the column means from here on.
    """
    url = scratch_database("panel_test_result_snapshot")
    config = _alembic_config(url)
    engine = create_engine(url)
    revision = "9430782bbec1"

    command.upgrade(config, f"{revision}-1")
    with engine.begin() as connection:
        connection.execute(
            sa.text("""
            INSERT INTO service (repo, name, branch) VALUES ('org/ecs', 'ecs', 'main');
            INSERT INTO job (service_id, kind, status, started_at, finished_at)
                SELECT id, 'scan', 'done', now(), now() FROM service;
            INSERT INTO job (service_id, kind, status, finished_at, error)
                SELECT id, 'scan', 'failed', now(), 'boom' FROM service;
            INSERT INTO snapshot (service_id, source_job_id, branch, commit_hash,
                    scanner_version, document_schema_version, analytics)
                SELECT s.id, j.id, 'main', repeat('a', 40), '0.1.0', '1', '{}'::jsonb
                FROM service s JOIN job j ON j.service_id = s.id
                WHERE j.status = 'done';
            """)
        )

    command.upgrade(config, revision)
    with engine.begin() as connection:
        rows = connection.execute(
            sa.text("""
            SELECT j.status, j.result_snapshot_id, s.id
            FROM job j LEFT JOIN snapshot s ON s.source_job_id = j.id
            ORDER BY j.id
            """)
        ).all()
        done, failed = rows
        assert done[1] == done[2] is not None  # linked to the one it created
        assert failed[1] is None  # nothing to point at

    command.downgrade(config, f"{revision}-1")
    with engine.begin() as connection:
        assert "result_snapshot_id" not in {
            column["name"] for column in inspect(engine).get_columns("job")
        }
        # The original direction is untouched, so nothing was lost either way.
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM snapshot WHERE source_job_id IS NOT NULL")
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_last_scanned_at_backfill_starts_from_created_at(scratch_database):
    """Every existing Snapshot was produced by a scan that succeeded at its
    ``created_at`` and has not been re-confirmed since, so that is its true
    value rather than a placeholder - which is why the column can be made NOT
    NULL in the same revision without leaving a row behind.
    """
    url = scratch_database("panel_test_last_scanned_at")
    config = _alembic_config(url)
    engine = create_engine(url)
    revision = "f1aec34a6321"

    command.upgrade(config, f"{revision}-1")
    with engine.begin() as connection:
        connection.execute(
            sa.text("""
            INSERT INTO service (repo, name, branch)
                VALUES ('org/ecs', 'ecs', 'main');
            INSERT INTO job (service_id, kind, status, started_at, finished_at)
                SELECT id, 'scan', 'done', now(), now() FROM service;
            INSERT INTO snapshot (service_id, source_job_id, branch, commit_hash,
                    scanner_version, document_schema_version, analytics, created_at)
                SELECT s.id, j.id, 'main', repeat('a', 40), '0.1.0', '1', '{}'::jsonb,
                    TIMESTAMPTZ '2026-01-01 10:00:00+00'
                FROM service s JOIN job j ON j.service_id = s.id;
            """)
        )

    command.upgrade(config, revision)
    with engine.begin() as connection:
        created, last_scanned = connection.execute(
            sa.text("SELECT created_at, last_scanned_at FROM snapshot")
        ).one()
        assert last_scanned == created == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        # NOT NULL with a server default, so a row inserted without one still
        # gets a real value rather than being rejected.
        connection.execute(
            sa.text("""
            INSERT INTO job (service_id, kind, status, started_at, finished_at)
                SELECT id, 'scan', 'done', now(), now() FROM service;
            INSERT INTO snapshot (service_id, source_job_id, branch, commit_hash,
                    scanner_version, document_schema_version, analytics)
                SELECT s.id, max(j.id), 'main', repeat('b', 40), '0.1.0', '1',
                    '{}'::jsonb
                FROM service s JOIN job j ON j.service_id = s.id
                GROUP BY s.id;
            """)
        )
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM snapshot WHERE last_scanned_at IS NULL")
            ).scalar_one()
            == 0
        )
    engine.dispose()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_endpoint_payload_roundtrip_is_lossless(db_session):
    endpoint = make_endpoint()
    _, _, snapshot = make_snapshot(db_session)
    db_session.add(
        DocumentRecord(
            snapshot_id=snapshot.id,
            payload=endpoint.model_dump(mode="json"),
            overall_status="partial",
            completeness=0.5,
            issues_count=1,
        )
    )
    db_session.flush()
    db_session.expire_all()

    record = db_session.scalars(select(DocumentRecord)).one()
    assert Endpoint.model_validate(record.payload) == endpoint
    # Generated projections come straight from the payload.
    assert record.kind == "endpoint"
    assert record.path == endpoint.path
    assert record.title == endpoint.title
    assert record.method == endpoint.method.value
    assert record.uri == endpoint.uri
    assert record.api_version == endpoint.api_version


def test_plain_document_payload_roundtrip(db_session):
    document = make_plain_document()
    _, _, snapshot = make_snapshot(db_session)
    db_session.add(
        DocumentRecord(
            snapshot_id=snapshot.id,
            payload=document.model_dump(mode="json"),
            overall_status="unsupported",
            completeness=None,
            issues_count=1,
        )
    )
    db_session.flush()
    db_session.expire_all()

    record = db_session.scalars(select(DocumentRecord)).one()
    restored = Document.model_validate(record.payload)
    assert restored == document
    assert restored.scan_result.failure_reason.code is (IssueCode.UNSUPPORTED_DOC_STYLE)
    assert record.kind == "document"
    assert record.method is None
    assert record.uri is None
    assert record.completeness is None


def test_document_kind_must_be_valid(db_session):
    _, _, snapshot = make_snapshot(db_session)
    db_session.add(
        DocumentRecord(
            snapshot_id=snapshot.id,
            payload={"kind": "mystery", "path": "x.rst"},
        )
    )
    with pytest.raises(IntegrityError, match="ck_document_kind_valid"):
        db_session.flush()


def test_document_path_unique_per_snapshot(db_session):
    endpoint = make_endpoint()
    _, _, snapshot = make_snapshot(db_session)
    for _ in range(2):
        db_session.add(
            DocumentRecord(
                snapshot_id=snapshot.id,
                payload=endpoint.model_dump(mode="json"),
            )
        )
    with pytest.raises(IntegrityError, match="uq_document_snapshot_path"):
        db_session.flush()


def test_service_repo_unique(db_session):
    db_session.add(Service(repo="org/dup", name="dup", branch="main"))
    db_session.add(Service(repo="org/dup", name="dup", branch="main"))
    with pytest.raises(IntegrityError, match="uq_service_repo"):
        db_session.flush()


def test_failed_job_requires_error(db_session):
    service = Service(repo="org/failing", name="failing", branch="main")
    db_session.add(service)
    db_session.flush()
    db_session.add(
        RepositoryScanJob(
            service_id=service.id,
            kind=JobKind.scan,
            status=JobStatus.failed,
            finished_at=sa.func.now(),
        )
    )
    with pytest.raises(IntegrityError, match="ck_job_failed_job_has_error"):
        db_session.flush()


def test_only_one_active_scan_job_per_service(db_session):
    service = Service(repo="org/busy", name="busy", branch="main")
    db_session.add(service)
    db_session.flush()
    db_session.add(RepositoryScanJob(service_id=service.id, kind=JobKind.scan))
    db_session.flush()
    db_session.add(RepositoryScanJob(service_id=service.id, kind=JobKind.scan))
    with pytest.raises(IntegrityError, match="uq_active_scan_job_per_service"):
        db_session.flush()


def test_snapshot_interruption_and_exclusions_survive(db_session):
    _, job, snapshot = make_snapshot(db_session)
    snapshot.excluded_documents = ["api-ref/source/out-of-date_apis/old.rst"]
    job.interruption = {
        "kind": "rate_limit",
        "repository": "opentelekomcloud-docs/ecs",
        "message": "API rate limit exceeded",
        "reset_time": 1789000000,
    }
    db_session.flush()
    db_session.expire_all()

    stored_job = db_session.get(RepositoryScanJob, job.id)
    assert stored_job.interruption["kind"] == "rate_limit"
    assert stored_job.interruption["reset_time"] == 1789000000
    stored_snapshot = db_session.get(Snapshot, snapshot.id)
    assert stored_snapshot.excluded_documents == [
        "api-ref/source/out-of-date_apis/old.rst"
    ]


def test_active_snapshot_link_set_null_on_delete(db_session):
    service, _, snapshot = make_snapshot(db_session)
    service.active_snapshot_id = snapshot.id
    service.latest_snapshot_id = snapshot.id
    db_session.flush()

    db_session.delete(snapshot)
    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(Service, service.id)
    assert stored.active_snapshot_id is None
    assert stored.latest_snapshot_id is None


def test_service_exclusion_roundtrip_and_cascade(db_session):
    service = Service(repo="org/legacy", name="legacy", branch="main")
    service.exclusion = ExcludedService(
        reason="repository archived upstream",
        excluded_by="valeriia",
    )
    db_session.add(service)
    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(Service, service.id)
    assert stored.exclusion.reason == "repository archived upstream"
    assert stored.exclusion.excluded_by == "valeriia"
    assert stored.exclusion.excluded_at is not None

    # Dropping the exclusion record makes the service eligible again.
    stored.exclusion = None
    db_session.flush()
    assert db_session.get(ExcludedService, service.id) is None


def test_job_initiated_by_defaults_to_system(db_session):
    service = Service(repo="org/auto", name="auto", branch="main")
    db_session.add(service)
    db_session.flush()
    job = RepositoryScanJob(service_id=service.id, kind=JobKind.scan)
    db_session.add(job)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(RepositoryScanJob, job.id).initiated_by == "system"


def test_job_enums_persist_as_their_wire_values(db_session):
    """The stored strings are the enum *values*, not the member names or ``str()``.

    ``JobKind``/``JobStatus`` are ``StrEnum`` (issue #87), which changed
    ``str(JobStatus.queued)`` from ``'JobStatus.queued'`` to ``'queued'``. The
    raw read below is what proves the column is unaffected: it bypasses the
    ORM's own enum coercion, so a base-class change that altered the persisted
    form would show up here rather than round-tripping invisibly through
    ``sa.Enum``.
    """
    service = Service(repo="org/wire", name="wire", branch="main")
    db_session.add(service)
    db_session.flush()
    job = RepositoryScanJob(
        service_id=service.id,
        kind=JobKind.scan,
        status=JobStatus.queued,
    )
    db_session.add(job)
    db_session.flush()

    stored = db_session.execute(
        sa.text("SELECT kind, status FROM job WHERE id = :id"), {"id": job.id}
    ).one()
    assert stored == ("scan", "queued")

    db_session.expire_all()
    reloaded = db_session.get(RepositoryScanJob, job.id)
    assert reloaded.kind is JobKind.scan
    assert reloaded.status is JobStatus.queued


def test_document_overall_status_must_be_valid(db_session):
    endpoint = make_endpoint()
    _, _, snapshot = make_snapshot(db_session)
    db_session.add(
        DocumentRecord(
            snapshot_id=snapshot.id,
            payload=endpoint.model_dump(mode="json"),
            overall_status="great",
        )
    )
    with pytest.raises(IntegrityError, match="ck_document_overall_status_valid"):
        db_session.flush()


def test_db_modules_import_without_database_or_github_token():
    """Importing the DB layer must not connect anywhere or need credentials."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"GITHUB_TOKEN", "DATABASE__URL", "TEST_DATABASE_URL"}
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import tools.panel.core.db.models, tools.panel.core.db.engine, "
            "tools.panel.core.db.base",
        ],
        env=environment,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
