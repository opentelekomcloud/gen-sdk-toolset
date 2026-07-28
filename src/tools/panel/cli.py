import argparse
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from tools.config import load_settings
from tools.panel.api.app import create_app
from tools.panel.core.db.engine import SessionLocal, get_engine
from tools.panel.core.db.models import Service
from tools.scanner.factory import build_doc_provider
from tools.scanner.repositories.discovery import (
    DiscoveredRepository,
    discover_repositories,
)

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
    the ones that have it. Repositories without it are **not** registered - the
    registry has no state for "looked at, not eligible" that the UI can show,
    so they would sit there as permanently unscanned services. They are printed
    instead, so the skip is visible rather than silent.

    An operational interruption (rate limit, auth) keeps everything checked so
    far and reports the reason with a non-zero exit code: a partial registry is
    fine, a partial registry that looks complete is not.
    """
    settings = load_settings()
    org = org or settings.github.org
    branch = branch or settings.github.branch

    result = discover_repositories(
        build_doc_provider(settings),
        org=org,
        api_ref_path=settings.scanner.api_ref_path,
        branch=branch,
    )
    eligible = [repo for repo in result.repositories if repo.has_api_ref]
    created, updated = _persist_discovered(eligible, branch=branch)

    print(
        f"checked {len(result.repositories)} repositories in {org}: "
        f"{len(eligible)} with {settings.scanner.api_ref_path} "
        f"({created} new, {updated} already registered)"
    )
    skipped = [repo.repo for repo in result.repositories if not repo.has_api_ref]
    if skipped:
        print(
            f"not registered ({len(skipped)}, no API reference): {', '.join(skipped)}"
        )

    if result.interruption is not None:
        print(
            f"discovery stopped early ({result.interruption.kind.value}): "
            f"{result.interruption.message}",
            file=sys.stderr,
        )
        return EXIT_INTERRUPTED
    return 0


def _persist_discovered(
    repositories: list[DiscoveredRepository], *, branch: str
) -> tuple[int, int]:
    """Insert or refresh one Service per eligible repository."""
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
            service.has_api_ref = True
            service.eligibility_checked_at = checked_at
        session.commit()
    return created, updated


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
