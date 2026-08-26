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
    """Answers the calls discovery makes, and can fail on a chosen repo.

    ``heads`` maps a repository to the branch HEAD it resolves to. A repository
    absent from it answers ``None`` (the ref does not exist), and one listed in
    ``head_errors`` raises - the two ways a lookup can fail to produce a commit.
    """

    def __init__(
        self,
        repos: list[str],
        with_api_ref: set[str],
        failing: str = "",
        heads: dict[str, str] | None = None,
        head_errors: set[str] = frozenset(),
    ):
        self.repos = repos
        self.with_api_ref = with_api_ref
        self.failing = failing
        self.heads = {} if heads is None else heads
        self.head_errors = head_errors
        self.head_calls: list[tuple[str, str]] = []

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

    def get_commit_hash(self, repo: str, branch: str) -> str | None:
        self.head_calls.append((repo, branch))
        if repo in self.head_errors:
            raise ProviderError(
                "API rate limit exceeded",
                kind=ProviderErrorKind.rate_limit,
                reset_time=1234,
            )
        return self.heads.get(repo)


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
    # The provider has just refused, so no HEAD lookups are attempted: they
    # could not succeed, and against a rate limit they would deepen it.
    assert provider.head_calls == []
    assert "branch HEADs not refreshed" in captured.out


# --------------------------------------------------------------------------- #
# Branch HEAD / drift (PS2-4)
# --------------------------------------------------------------------------- #
HEAD_A = "a" * 40
HEAD_B = "b" * 40


def _head_of(session_factory, repo: str) -> str | None:
    with session_factory() as session:
        return session.scalar(select(Service).where(Service.repo == repo)).head_commit


def test_discovery_stores_the_branch_head_of_eligible_repositories(
    session_factory, monkeypatch
):
    provider = FakeProvider(
        repos=[f"{ORG}/ecs"], with_api_ref={f"{ORG}/ecs"}, heads={f"{ORG}/ecs": HEAD_A}
    )

    _run(monkeypatch, provider)

    assert _head_of(session_factory, f"{ORG}/ecs") == HEAD_A
    # Resolved against the configured branch, not a default.
    assert provider.head_calls == [(f"{ORG}/ecs", "main")]


def test_discovery_refreshes_the_head_on_a_later_run(session_factory, monkeypatch):
    """Drift is only as current as the last HEAD read, so a repeat run has to
    move it - otherwise a repository that moved on would keep reporting the
    commit it had when it was first discovered."""
    _run(
        monkeypatch,
        FakeProvider(
            repos=[f"{ORG}/ecs"],
            with_api_ref={f"{ORG}/ecs"},
            heads={f"{ORG}/ecs": HEAD_A},
        ),
    )

    _run(
        monkeypatch,
        FakeProvider(
            repos=[f"{ORG}/ecs"],
            with_api_ref={f"{ORG}/ecs"},
            heads={f"{ORG}/ecs": HEAD_B},
        ),
    )

    assert _head_of(session_factory, f"{ORG}/ecs") == HEAD_B


def test_an_unresolvable_ref_keeps_the_head_already_stored(
    session_factory, monkeypatch, capsys
):
    """A ref that does not resolve is a fact about one repository, not about the
    provider: the run carries on, and the stored HEAD stays. Dropping it would
    retract a drift flag the panel is still entitled to raise."""
    _run(
        monkeypatch,
        FakeProvider(
            repos=[f"{ORG}/ecs"],
            with_api_ref={f"{ORG}/ecs"},
            heads={f"{ORG}/ecs": HEAD_A},
        ),
    )
    capsys.readouterr()

    exit_code = _run(
        monkeypatch,
        FakeProvider(repos=[f"{ORG}/ecs"], with_api_ref={f"{ORG}/ecs"}, heads={}),
    )

    assert exit_code == 0
    assert _head_of(session_factory, f"{ORG}/ecs") == HEAD_A  # untouched
    # The skip is visible, not just logged: the drift flag now answers from an
    # older reading and the operator has to be able to tell.
    assert "branch HEAD unresolved for 1" in capsys.readouterr().out


def test_a_rate_limit_stops_head_resolution_instead_of_hammering_on(
    session_factory, monkeypatch, capsys
):
    """An operational failure means the provider is refusing, so every later
    lookup fails the same way. Continuing would spend a request per remaining
    repository to learn that N times, and on a rate limit would deepen it - so
    the walk stops where it is, keeps what it resolved, and exits non-zero
    rather than reporting a refresh that only half happened."""
    provider = FakeProvider(
        repos=[f"{ORG}/aaa", f"{ORG}/bbb", f"{ORG}/ccc"],
        with_api_ref={f"{ORG}/aaa", f"{ORG}/bbb", f"{ORG}/ccc"},
        heads={f"{ORG}/aaa": HEAD_A},
        head_errors={f"{ORG}/bbb"},
    )

    exit_code = _run(monkeypatch, provider)

    assert exit_code == cli.EXIT_INTERRUPTED
    # aaa resolved, bbb refused, ccc never asked.
    assert [repo for repo, _branch in provider.head_calls] == [
        f"{ORG}/aaa",
        f"{ORG}/bbb",
    ]
    assert _head_of(session_factory, f"{ORG}/aaa") == HEAD_A  # progress kept
    assert _head_of(session_factory, f"{ORG}/ccc") is None
    captured = capsys.readouterr()
    assert "branch HEAD resolution stopped early (rate_limit)" in captured.err


def test_the_head_is_read_from_the_branch_the_service_is_scanned_at(
    session_factory, monkeypatch
):
    """The runner scans `job.service.branch`, which a discovery run pointed at
    a different branch must not override. Reading HEAD from the other branch
    would compare a commit taken on one against a snapshot taken on the other,
    and drift would be stuck on forever - no scan could make them agree."""
    with session_factory() as session:
        session.add(Service(repo=f"{ORG}/pinned", name="pinned", branch="stable"))
        session.commit()

    provider = FakeProvider(
        repos=[f"{ORG}/pinned"],
        with_api_ref={f"{ORG}/pinned"},
        heads={f"{ORG}/pinned": HEAD_B},
    )
    _run(monkeypatch, provider)  # _run passes branch "main"

    assert provider.head_calls == [(f"{ORG}/pinned", "stable")]
    assert _head_of(session_factory, f"{ORG}/pinned") == HEAD_B
    with session_factory() as session:
        # Discovery reads the stored branch; it does not rewrite it.
        assert session.scalars(select(Service)).one().branch == "stable"


def test_an_ineligible_repository_gets_no_head_lookup(session_factory, monkeypatch):
    """A repository with no API reference cannot be scanned, so it has no scan
    to drift from - spending a request per run on its HEAD would buy nothing."""
    provider = FakeProvider(
        repos=[f"{ORG}/website"], with_api_ref=set(), heads={f"{ORG}/website": HEAD_A}
    )

    _run(monkeypatch, provider)

    assert provider.head_calls == []
    assert _head_of(session_factory, f"{ORG}/website") is None


# --------------------------------------------------------------------------- #
# Scheduled re-runs
# --------------------------------------------------------------------------- #


def test_repeated_discovery_runs_change_nothing_but_the_marks(
    session_factory, monkeypatch, capsys
):
    """What a cron entry does to this registry, three passes in: the rows are
    the same rows, and only the two marks a pass exists to refresh move. A run
    that added a second Service for a repository it had already seen would grow
    the registry by one row every interval, and each copy would look plausible.
    """
    heads = [HEAD_A, HEAD_B, "c" * 40]
    for head in heads:
        _run(
            monkeypatch,
            FakeProvider(
                repos=[f"{ORG}/ecs", f"{ORG}/website"],
                with_api_ref={f"{ORG}/ecs"},
                heads={f"{ORG}/ecs": head},
            ),
        )

    assert _registered(session_factory) == [f"{ORG}/ecs", f"{ORG}/website"]
    with session_factory() as session:
        ecs = session.scalar(select(Service).where(Service.repo == f"{ORG}/ecs"))
        assert ecs.head_commit == heads[-1]  # compared against the newest read
        # Seen once, checked three times: a pass that re-stamped first_seen
        # would report every repository as new on every interval.
        assert ecs.first_seen < ecs.eligibility_checked_at
    assert _eligibility(session_factory) == {
        f"{ORG}/ecs": True,
        f"{ORG}/website": False,
    }
    assert "0 new, 2 already registered" in capsys.readouterr().out


def test_discovery_starts_no_scan_job(session_factory, monkeypatch):
    """The product decision the schedule rests on: a pass refreshes marks, and
    nothing else. A scan enqueued here would run unattended on every interval,
    spending the token's quota with no operator behind it."""
    _run(
        monkeypatch,
        FakeProvider(
            repos=[f"{ORG}/ecs", f"{ORG}/website"],
            with_api_ref={f"{ORG}/ecs"},
            heads={f"{ORG}/ecs": HEAD_A},
        ),
    )

    # Asserted first, so an empty job table cannot pass this test by way of a
    # pass that did nothing at all.
    assert _registered(session_factory) == [f"{ORG}/ecs", f"{ORG}/website"]
    with session_factory() as session:
        assert session.scalars(select(RepositoryScanJob)).all() == []
        assert session.scalars(select(Snapshot)).all() == []


def test_the_summary_reports_how_many_heads_were_refreshed(
    session_factory, monkeypatch, capsys
):
    """The counter a scheduled run is read for. Reported on every pass, zero
    included: a log line that only appears when something worked cannot show a
    registry going stale."""
    _run(
        monkeypatch,
        FakeProvider(
            repos=[f"{ORG}/ecs", f"{ORG}/vpc", f"{ORG}/website"],
            with_api_ref={f"{ORG}/ecs", f"{ORG}/vpc"},
            heads={f"{ORG}/ecs": HEAD_A, f"{ORG}/vpc": HEAD_B},
        ),
    )

    assert "branch HEAD refreshed for 2 of 2 eligible" in capsys.readouterr().out


def test_the_refreshed_count_is_printed_even_when_nothing_resolved(
    session_factory, monkeypatch, capsys
):
    exit_code = _run(
        monkeypatch,
        FakeProvider(repos=[f"{ORG}/ecs"], with_api_ref={f"{ORG}/ecs"}, heads={}),
    )

    assert exit_code == 0  # an unresolved ref is not an interruption
    assert "branch HEAD refreshed for 0 of 1 eligible" in capsys.readouterr().out
