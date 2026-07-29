"""Seeding the panel registry from the CLI (issue #16).

Discovery talks to a hand-written fake provider, so nothing here needs GitHub;
the database comes from tests/test_panel_db.py's PostgreSQL provisioning.
"""

from __future__ import annotations

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
from tools.panel.core.db.models import Service  # noqa: E402
from tools.shared.exceptions import ProviderError, ProviderErrorKind  # noqa: E402

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


def test_discovery_registers_only_repositories_with_an_api_reference(
    session_factory, monkeypatch, capsys
):
    """A repository without the API-reference path is reported, not registered:
    the registry has no state the UI could show for it."""
    provider = FakeProvider(
        repos=[f"{ORG}/ecs", f"{ORG}/website", f"{ORG}/vpc"],
        with_api_ref={f"{ORG}/ecs", f"{ORG}/vpc"},
    )

    exit_code = _run(monkeypatch, provider)

    assert exit_code == 0
    assert _registered(session_factory) == [f"{ORG}/ecs", f"{ORG}/vpc"]
    output = capsys.readouterr().out
    assert "checked 3 repositories" in output
    assert f"{ORG}/website" in output  # the skip is visible


def test_discovery_records_eligibility_metadata(session_factory, monkeypatch):
    _run(monkeypatch, FakeProvider([f"{ORG}/ecs"], {f"{ORG}/ecs"}))

    with session_factory() as session:
        service = session.scalars(select(Service)).one()
        assert service.name == "ecs"  # derived from the repository
        assert service.branch == "main"
        assert service.has_api_ref is True
        assert service.first_seen is not None
        assert service.eligibility_checked_at is not None


def test_rerunning_discovery_updates_instead_of_duplicating(
    session_factory, monkeypatch, capsys
):
    provider = FakeProvider([f"{ORG}/ecs"], {f"{ORG}/ecs"})
    _run(monkeypatch, provider)
    capsys.readouterr()

    _run(monkeypatch, provider)

    assert _registered(session_factory) == [f"{ORG}/ecs"]
    assert "0 new, 1 already registered" in capsys.readouterr().out


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
