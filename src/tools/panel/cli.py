import argparse
import json

from sqlalchemy import select

from tools.panel.api.app import create_app
from tools.panel.core.db.engine import SessionLocal, get_engine
from tools.panel.core.db.models import Service

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

    args = parser.parse_args()
    if args.command == "openapi":
        _openapi_command()
    elif args.command == "register-service":
        _register_command(args.repo, args.name, args.branch)


if __name__ == "__main__":
    main()
