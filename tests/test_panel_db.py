"""PostgreSQL-backed tests for the panel persistence layer.

Database resolution order:

1. ``TEST_DATABASE_URL`` environment variable (an admin PostgreSQL URL whose
   role may create/drop scratch databases), e.g.
   ``postgresql+psycopg://panel:panel@localhost:5432/panel``;
2. otherwise a throwaway ``postgres:16-alpine`` container via testcontainers
   (requires a Docker daemon).

Without either, the module is skipped.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
    Generation,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
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


@pytest.fixture(scope="session")
def admin_url() -> str:
    """Admin PostgreSQL URL used to create scratch databases."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return

    docker = pytest.importorskip(
        "testcontainers.postgres",
        reason="TEST_DATABASE_URL is not set and testcontainers is unavailable",
    )
    try:
        container = docker.PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except Exception as error:  # docker daemon missing/unreachable
        pytest.skip(f"TEST_DATABASE_URL is not set and Docker is unavailable: {error}")
    yield container.get_connection_url()
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


def make_generation(session: Session, repo: str = "opentelekomcloud-docs/ecs"):
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
    generation = Generation(
        service_id=service.id,
        source_job_id=job.id,
        branch="main",
        commit_hash="a" * 40,
        scanner_version="0.1.0",
        document_schema_version=DOCUMENT_SCHEMA_VERSION,
        analytics={},
    )
    session.add(generation)
    session.flush()
    return service, job, generation


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


def test_migration_upgrade_creates_schema_and_downgrade_removes_it(scratch_database):
    url = scratch_database("panel_test_migrations")
    config = _alembic_config(url)
    engine = create_engine(url)

    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert {"service", "excluded_service", "job", "generation", "document"} <= set(
        inspector.get_table_names()
    )
    service_fks = {fk["name"] for fk in inspector.get_foreign_keys("service")}
    assert {"fk_service_active_generation", "fk_service_latest_generation"} <= (
        service_fks
    )
    document_columns = {column["name"] for column in inspector.get_columns("document")}
    assert {"payload", "kind", "path", "method", "uri", "completeness"} <= (
        document_columns
    )

    command.downgrade(config, "base")
    inspector = inspect(engine)
    assert not {"service", "excluded_service", "job", "generation", "document"} & set(
        inspector.get_table_names()
    )
    engine.dispose()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_endpoint_payload_roundtrip_is_lossless(db_session):
    endpoint = make_endpoint()
    _, _, generation = make_generation(db_session)
    db_session.add(
        DocumentRecord(
            generation_id=generation.id,
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
    _, _, generation = make_generation(db_session)
    db_session.add(
        DocumentRecord(
            generation_id=generation.id,
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
    _, _, generation = make_generation(db_session)
    db_session.add(
        DocumentRecord(
            generation_id=generation.id,
            payload={"kind": "mystery", "path": "x.rst"},
        )
    )
    with pytest.raises(IntegrityError, match="ck_document_kind_valid"):
        db_session.flush()


def test_document_path_unique_per_generation(db_session):
    endpoint = make_endpoint()
    _, _, generation = make_generation(db_session)
    for _ in range(2):
        db_session.add(
            DocumentRecord(
                generation_id=generation.id,
                payload=endpoint.model_dump(mode="json"),
            )
        )
    with pytest.raises(IntegrityError, match="uq_document_generation_path"):
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


def test_generation_interruption_and_exclusions_survive(db_session):
    _, job, generation = make_generation(db_session)
    generation.incomplete_reason = "rate limited"
    generation.excluded_documents = ["api-ref/source/out-of-date_apis/old.rst"]
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
    stored_generation = db_session.get(Generation, generation.id)
    assert stored_generation.excluded_documents == [
        "api-ref/source/out-of-date_apis/old.rst"
    ]


def test_active_generation_link_set_null_on_delete(db_session):
    service, _, generation = make_generation(db_session)
    service.active_generation_id = generation.id
    service.latest_generation_id = generation.id
    db_session.flush()

    db_session.delete(generation)
    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(Service, service.id)
    assert stored.active_generation_id is None
    assert stored.latest_generation_id is None


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


def test_document_overall_status_must_be_valid(db_session):
    endpoint = make_endpoint()
    _, _, generation = make_generation(db_session)
    db_session.add(
        DocumentRecord(
            generation_id=generation.id,
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
