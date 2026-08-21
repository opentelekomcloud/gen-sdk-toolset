import argparse
import json
import logging
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tools.config import load_settings
from tools.panel.api.app import create_app
from tools.panel.core.db.engine import SessionLocal, get_engine
from tools.panel.core.db.models import ExcludedService, Service, Snapshot
from tools.scanner.factory import build_doc_provider
from tools.scanner.interfaces import DocProvider
from tools.scanner.repositories.discovery import (
    DiscoveredRepository,
    discover_repositories,
)
from tools.shared.exceptions import ProviderError

logger = logging.getLogger(__name__)

EXIT_INTERRUPTED = 1


def _openapi_command() -> None:
    app = create_app()
    schema = app.openapi()
    print(json.dumps(schema, indent=2, sort_keys=True))


def _register_command(repo: str, name: str | None, branch: str) -> None:
    """Register a repository so the panel can scan it.

    Repository discovery (issue #64) will fill the registry automatically; until
    then a service is put there by hand. Registering a repository that is
    already known prints its id instead of failing, so the command is safe to
    re-run.
    """
    get_engine()
    with SessionLocal() as session:
        existing = session.scalar(select(Service).where(Service.repo == repo))
        if existing is not None:
            print(f"{repo} is already registered (id={existing.id})")
            return
        service = Service(repo=repo, name=name or repo.split("/")[-1], branch=branch)
        session.add(service)
        session.commit()
        session.refresh(service)
        print(f"registered {repo} (id={service.id})")


def _discover_command(org: str | None, branch: str | None) -> int:
    """Fill the registry from an organization's repositories.

    Checks every repository for the configured API-reference path and registers
    all of them, eligible or not. An ineligible repository is stored with
    ``has_api_ref = False`` rather than skipped: the registry now has a state
    for "looked at, not eligible", so the result of the check is kept instead
    of being printed once and forgotten. The read endpoints hide those rows
    from the registry and serve them from ``/api/scan/ineligible``.

    An operational interruption (rate limit, auth) keeps everything checked so
    far and reports the reason with a non-zero exit code: a partial registry is
    fine, a partial registry that looks complete is not.
    """
    settings = load_settings()
    org = org or settings.github.org
    branch = branch or settings.github.branch

    provider = build_doc_provider(settings)
    result = discover_repositories(
        provider,
        org=org,
        api_ref_path=settings.scanner.api_ref_path,
        branch=branch,
    )
    eligible = [repo for repo in result.repositories if repo.has_api_ref]
    # Resolved before the session opens: these are network calls, and the
    # persistence loop below runs inside one transaction.
    #
    # Skipped entirely once discovery has been interrupted. The provider has
    # just refused - the loop stops on the first operational failure - so one
    # lookup per eligible repository would be a burst of calls that cannot
    # succeed, and against a rate limit it would only dig the hole deeper.
    heads: dict[str, str] = {}
    unresolved: list[str] = []
    if result.interruption is None:
        heads, unresolved = _resolve_heads(
            provider, [repo.repo for repo in eligible], branch=branch
        )
    created, updated = _persist_discovered(
        result.repositories, branch=branch, heads=heads
    )

    print(
        f"checked {len(result.repositories)} repositories in {org}: "
        f"{len(eligible)} with {settings.scanner.api_ref_path}, "
        f"{len(result.repositories) - len(eligible)} without "
        f"({created} new, {updated} already registered)"
    )
    if unresolved:
        # Printed, not only logged: each of these keeps whatever head_commit it
        # had, so its drift flag is now answering from an older reading.
        print(
            f"branch HEAD unresolved for {len(unresolved)}, "
            f"drift not refreshed: {', '.join(unresolved)}"
        )

    if result.interruption is not None:
        # Every stored head_commit is now from an earlier run, so the drift
        # flags this registry shows are as old as the last complete discovery.
        print("branch HEADs not refreshed: discovery stopped early")
        print(
            f"discovery stopped early ({result.interruption.kind.value}): "
            f"{result.interruption.message}",
            file=sys.stderr,
        )
        return EXIT_INTERRUPTED
    return 0


def _resolve_heads(
    provider: DocProvider, repos: list[str], *, branch: str
) -> tuple[dict[str, str], list[str]]:
    """Resolve the branch HEAD of each repository, before any session is open.

    Every call here is a network round trip, so this runs with no transaction
    held - the persistence loop below is one transaction over local work only.

    A repository whose HEAD cannot be read is returned in the second list
    rather than mapped to ``None``. The caller must leave such a service's
    stored ``head_commit`` alone: clearing it would silently retract a drift
    flag, and writing a guess would invent one. A lookup failure is also not
    fatal - discovery has already learned what it came for, and one
    unreadable ref should not throw that away.
    """
    heads: dict[str, str] = {}
    unresolved: list[str] = []
    for repo in repos:
        try:
            head = provider.get_commit_hash(repo, branch)
        except ProviderError as error:
            logger.warning("Could not resolve %s@%s: %s", repo, branch, error)
            unresolved.append(repo)
            continue
        if head is None:
            logger.warning("No commit resolved for %s@%s", repo, branch)
            unresolved.append(repo)
            continue
        heads[repo] = head
    return heads, unresolved


def _persist_discovered(
    repositories: list[DiscoveredRepository], *, branch: str, heads: dict[str, str]
) -> tuple[int, int]:
    """Insert or refresh one Service per discovered repository, eligible or not.

    The same row is reused across runs, so a repository that gains an API
    reference later keeps its ``Service.id`` - and with it its job history -
    instead of being registered a second time.
    """
    get_engine()
    created = 0
    updated = 0
    checked_at = datetime.now(tz=UTC)
    with SessionLocal() as session:
        for discovered in repositories:
            service = session.scalar(
                select(Service).where(Service.repo == discovered.repo)
            )
            if service is None:
                service = Service(
                    repo=discovered.repo,
                    name=discovered.repo.split("/")[-1],
                    branch=branch,
                    first_seen=checked_at,
                )
                session.add(service)
                created += 1
            else:
                updated += 1

            blocked_by = (
                None if discovered.has_api_ref else _demotion_blocked(session, service)
            )
            if blocked_by is None:
                service.has_api_ref = discovered.has_api_ref
            else:
                logger.warning(
                    "Found no API reference for %s but leaving its eligibility "
                    "at %r: %s",
                    discovered.repo,
                    service.has_api_ref,
                    blocked_by,
                )
            service.eligibility_checked_at = checked_at
            # Only ever written from a HEAD that resolved. A repository missing
            # from `heads` keeps the one it had: the drift flag it feeds is a
            # claim about the documentation, and a failed lookup is no evidence
            # either way.
            head = heads.get(discovered.repo)
            if head is not None:
                service.head_commit = head
        session.commit()
    return created, updated


def _demotion_blocked(session: Session, service: Service) -> str | None:
    """Why this Service may not be marked ineligible, or None if it may.

    A discovery run sees one branch at one moment, and a lookup that comes back
    empty is not always the repository having lost its documentation - a moved
    default branch or a renamed path reads exactly the same. Where the panel
    holds evidence that someone worked with this service, that evidence outvotes
    a single check: marking it ineligible would drop it out of the registry, and
    with it a scan history nothing else links to.

    A Service being inserted right now has neither, so it is never blocked.
    """
    if service.id is None:
        return None
    if (
        session.scalar(
            select(Snapshot.id).where(Snapshot.service_id == service.id).limit(1)
        )
        is not None
    ):
        return "it already has a stored snapshot"
    if (
        session.scalar(
            select(ExcludedService.service_id).where(
                ExcludedService.service_id == service.id
            )
        )
        is not None
    ):
        return "it is excluded, which is an operator's decision to keep"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(prog="panel")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("openapi", help="Print the OpenAPI schema to stdout.")

    register = subparsers.add_parser(
        "register-service", help="Add a repository to the panel registry."
    )
    register.add_argument("repo", help="Repository as owner/name.")
    register.add_argument("--name", help="Display name (default: the repo's name).")
    register.add_argument("--branch", default="main", help="Branch to scan.")

    discover = subparsers.add_parser(
        "discover", help="Register every eligible repository of an organization."
    )
    discover.add_argument("--org", help="GitHub organization (default: [github].org).")
    discover.add_argument(
        "--branch", help="Branch to check (default: [github].branch)."
    )

    args = parser.parse_args()
    if args.command == "openapi":
        _openapi_command()
    elif args.command == "register-service":
        _register_command(args.repo, args.name, args.branch)
    elif args.command == "discover":
        raise SystemExit(_discover_command(args.org, args.branch))


if __name__ == "__main__":
    main()
