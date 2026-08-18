"""Seeding the panel registry from the CLI (issue #16).

Discovery talks to a hand-written fake provider, so nothing here needs GitHub;
the database comes from tests/test_panel_db.py's PostgreSQL provisioning.
"""

from __future__ import annotations

import logging
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
    scratch_database,
)
from tools.panel import cli  # noqa: E402
from tools.panel.core.db.models import (  # noqa: E402
    ExcludedService,
    JobKind,
    JobStatus,
    RepositoryScanJob,
    Service,
    Snapshot,
)
from tools.shared.exceptions import ProviderError, ProviderErrorKind  # noqa: E402
from tools.shared.ir import DOCUMENT_SCHEMA_VERSION  # noqa: E402

ORG = "opentelekomcloud-docs"
API_REF = "api-ref/source"


@pytest.fixture
def engine(scratch_database):  # noqa: F811  (pytest fixture injection)
    url = scratch_database("panel_test_registry_cli")
    command.upgrade(_alembic_config(url), "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def bound_cli(session_factory, monkeypatch):
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    monkeypatch.setattr(cli, "get_engine", lambda: None)


class FakeProvider:
    """Answers the two calls discovery makes, and can fail on a chosen repo."""

    def __init__(self, repos: list[str], with_api_ref: set[str], failing: str = ""):
        self.repos = repos
        self.with_api_ref = with_api_ref
        self.failing = failing

    def list_repos(self, org: str) -> list[str]:
        assert org == ORG
        return self.repos

    def path_exists(self, repo: str, ref: str, path: str) -> bool:
        if repo == self.failing:
            raise ProviderError(
                "API rate limit exceeded",
                kind=ProviderErrorKind.rate_limit,
                reset_time=1234,
            )
        assert path == API_REF
        return repo in self.with_api_ref


def _run(monkeypatch, provider: FakeProvider) -> int:
    monkeypatch.setattr(cli, "build_doc_provider", lambda _settings: provider)
    return cli._discover_command(ORG, "main")


def _registered(session_factory) -> list[str]:
    with session_factory() as session:
        return [
            service.repo
            for service in session.scalars(select(Service).order_by(Service.repo)).all()
        ]


def _eligibility(session_factory) -> dict[str, bool | None]:
    with session_factory() as session:
        return {
            service.repo: service.has_api_ref
            for service in session.scalars(select(Service)).all()
        }


def test_discovery_registers_every_repository_it_checked(
    session_factory, monkeypatch, capsys
):
    """Ineligible repositories are stored rather than printed and forgotten.

    They used to be skipped, because the registry had no state for "looked at,
    not eligible". It has one now (``has_api_ref = False``), so the result of
    the check is kept: an operator can see the repository was examined instead
    of wondering whether discovery ever reached it.
    """
    provider = FakeProvider(
        repos=[f"{ORG}/ecs", f"{ORG}/website", f"{ORG}/vpc"],
        with_api_ref={f"{ORG}/ecs", f"{ORG}/vpc"},
    )

    exit_code = _run(monkeypatch, provider)

    assert exit_code == 0
    assert _registered(session_factory) == [
        f"{ORG}/ecs",
        f"{ORG}/vpc",
        f"{ORG}/website",
    ]
    assert _eligibility(session_factory) == {
        f"{ORG}/ecs": True,
        f"{ORG}/vpc": True,
        f"{ORG}/website": False,
    }
    output = capsys.readouterr().out
    assert "checked 3 repositories" in output
    assert "2 with api-ref/source, 1 without" in output
    assert "not registered" not in output


def test_discovery_records_eligibility_metadata(session_factory, monkeypatch):
    _run(monkeypatch, FakeProvider([f"{ORG}/ecs"], {f"{ORG}/ecs"}))

    with session_factory() as session:
        service = session.scalars(select(Service)).one()
        assert service.name == "ecs"  # derived from the repository
        assert service.branch == "main"
        assert service.has_api_ref is True
        assert service.first_seen is not None
        assert service.eligibility_checked_at is not None


def test_discovery_records_an_ineligible_repository_as_checked_not_unknown(
    session_factory, monkeypatch
):
    """False and NULL are different claims: False means discovery looked and
    found nothing, NULL means it never looked. Storing the ineligible one as
    NULL would leave it in the registry as a permanently unscannable service."""
    _run(monkeypatch, FakeProvider([f"{ORG}/website"], set()))

    with session_factory() as session:
        service = session.scalars(select(Service)).one()
        assert service.has_api_ref is False
        assert service.eligibility_checked_at is not None
        assert service.first_seen is not None


def test_rerunning_discovery_updates_instead_of_duplicating(
    session_factory, monkeypatch, capsys
):
    provider = FakeProvider([f"{ORG}/ecs"], {f"{ORG}/ecs"})
    _run(monkeypatch, provider)
    capsys.readouterr()

    _run(monkeypatch, provider)

    assert _registered(session_factory) == [f"{ORG}/ecs"]
    assert "0 new, 1 already registered" in capsys.readouterr().out


def test_rerunning_discovery_refreshes_the_eligibility_timestamp(
    session_factory, monkeypatch
):
    """The timestamp is how ``/scan/ineligible`` says how stale a finding is,
    so a repeat run has to move it even when the verdict does not change."""
    provider = FakeProvider([f"{ORG}/website"], set())
    _run(monkeypatch, provider)
    with session_factory() as session:
        first = session.scalars(select(Service)).one().eligibility_checked_at

    _run(monkeypatch, provider)

    with session_factory() as session:
        service = session.scalars(select(Service)).one()
        assert service.eligibility_checked_at > first
        assert service.first_seen < service.eligibility_checked_at


def test_a_repository_that_gains_an_api_reference_keeps_its_service_id(
    session_factory, monkeypatch
):
    """The same row is reused, so the job history and any snapshot survive the
    promotion. Registering a second Service for the same repo would strand
    everything already attached to the first."""
    _run(monkeypatch, FakeProvider([f"{ORG}/ecs"], set()))
    with session_factory() as session:
        service = session.scalars(select(Service)).one()
        original_id, first_seen = service.id, service.first_seen
        assert service.has_api_ref is False

    _run(monkeypatch, FakeProvider([f"{ORG}/ecs"], {f"{ORG}/ecs"}))

    with session_factory() as session:
        service = session.scalars(select(Service)).one()
        assert service.id == original_id
        assert service.has_api_ref is True
        assert service.first_seen == first_seen  # not re-stamped as newly seen


def _seed_snapshot(session_factory, repo: str) -> None:
    with session_factory() as session:
        service = session.scalar(select(Service).where(Service.repo == repo))
        job = RepositoryScanJob(
            service_id=service.id,
            kind=JobKind.scan,
            status=JobStatus.done,
            started_at=datetime.now(tz=UTC),
            finished_at=datetime.now(tz=UTC),
        )
        session.add(job)
        session.flush()
        session.add(
            Snapshot(
                service_id=service.id,
                source_job_id=job.id,
                branch="main",
                commit_hash="a" * 40,
                scanner_version="0.1.0",
                document_schema_version=DOCUMENT_SCHEMA_VERSION,
                analytics={},
            )
        )
        session.commit()


@pytest.mark.parametrize("state", ["snapshot", "exclusion"])
def test_discovery_will_not_demote_a_service_the_panel_has_state_for(
    session_factory, monkeypatch, caplog, state
):
    """One empty lookup is not proof the documentation is gone - a moved default
    branch or a renamed path reads identically. Where the panel already holds a
    snapshot or an operator's exclusion, that outvotes a single check: demoting
    would drop the row out of the registry and take a scan history with it.
    """
    _run(monkeypatch, FakeProvider([f"{ORG}/ecs"], {f"{ORG}/ecs"}))
    if state == "snapshot":
        _seed_snapshot(session_factory, f"{ORG}/ecs")
    else:
        with session_factory() as session:
            service = session.scalar(
                select(Service).where(Service.repo == f"{ORG}/ecs")
            )
            session.add(
                ExcludedService(
                    service_id=service.id, reason="retired", excluded_by="operator"
                )
            )
            session.commit()

    with caplog.at_level(logging.WARNING):
        _run(monkeypatch, FakeProvider([f"{ORG}/ecs"], set()))

    with session_factory() as session:
        service = session.scalars(select(Service)).one()
        assert service.has_api_ref is True  # not demoted
        # The check still ran, and the row records that it did.
        assert service.eligibility_checked_at is not None
    assert f"Found no API reference for {ORG}/ecs" in caplog.text


def test_the_guard_protects_a_scanned_service_that_was_never_discovered(
    session_factory, monkeypatch
):
    """A hand-registered service starts at NULL, not True. Once it has been
    scanned, a later empty lookup must still not push it to False - that would
    drop a service holding a stored snapshot out of the registry, and the value
    it keeps is "unknown", not "eligible"."""
    with session_factory() as session:
        session.add(Service(repo=f"{ORG}/manual", name="manual", branch="main"))
        session.commit()
    _seed_snapshot(session_factory, f"{ORG}/manual")

    _run(monkeypatch, FakeProvider([f"{ORG}/manual"], set()))

    with session_factory() as session:
        service = session.scalars(select(Service)).one()
        assert service.has_api_ref is None
        assert service.eligibility_checked_at is not None


def test_discovery_demotes_a_service_with_nothing_attached(
    session_factory, monkeypatch
):
    """The guard is not a blanket refusal: a service that was only ever
    discovered, never scanned and never excluded, follows the latest check."""
    _run(monkeypatch, FakeProvider([f"{ORG}/ecs"], {f"{ORG}/ecs"}))

    _run(monkeypatch, FakeProvider([f"{ORG}/ecs"], set()))

    with session_factory() as session:
        assert session.scalars(select(Service)).one().has_api_ref is False


def test_interrupted_discovery_keeps_its_progress_and_reports_the_reason(
    session_factory, monkeypatch, capsys
):
    """A rate limit must not look like a completed discovery: what was checked
    is kept, and the command exits non-zero with the reason."""
    provider = FakeProvider(
        repos=[f"{ORG}/ecs", f"{ORG}/blocked", f"{ORG}/never-reached"],
        with_api_ref={f"{ORG}/ecs", f"{ORG}/never-reached"},
        failing=f"{ORG}/blocked",
    )

    exit_code = _run(monkeypatch, provider)

    assert exit_code == cli.EXIT_INTERRUPTED
    assert _registered(session_factory) == [f"{ORG}/ecs"]  # progress kept
    captured = capsys.readouterr()
    assert "rate_limit" in captured.err
    assert "API rate limit exceeded" in captured.err
