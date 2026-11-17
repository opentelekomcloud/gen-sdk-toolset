"""CLI entry point: scan one OTC docs repository and emit a JSON result.

With ``--path`` the repository is read from a local git working copy, and a
markdown report of documentation errors is printed to stdout as well.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError

from tools.config import Settings, load_settings
from tools.scanner.doc_checks import find_doc_errors, render_markdown
from tools.scanner.factory import build_local_scanner, build_scanner
from tools.scanner.local import LocalDocProvider, LocalSourceError
from tools.shared.ir import Service
from tools.shared.scan import RepositoryScanResult

# Exit codes
EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gen-sdk-scan",
        description=(
            "Scan one OTC documentation repository and emit a JSON result "
            "of discovered API endpoints and per-document parse results."
        ),
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to TOML config file (default: scan-config.toml in CWD).",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help=(
            "Output JSON file path. Overrides [output].path from the config. "
            "Pass '-' to skip the file and emit the report to stdout instead."
        ),
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--repo",
        metavar="OWNER/NAME",
        help="GitHub repository to scan. Emits one RepositoryScanResult.",
    )
    target.add_argument(
        "--path",
        metavar="DIR",
        help=(
            "Local git working copy to scan, files as they are on disk. "
            "Needs no GITHUB_TOKEN. Prints a markdown report of documentation "
            "errors to stdout."
        ),
    )
    parser.add_argument(
        "--branch",
        metavar="NAME",
        help="Git branch to scan. Overrides [github].branch. Not with --path.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the JSON report to stdout (in addition to writing the file).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging (DEBUG).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Quiet logging (WARNING).",
    )
    return parser


def _resolve_log_level(settings: Settings, verbose: bool, quiet: bool) -> str:
    if verbose:
        return "DEBUG"
    if quiet:
        return "WARNING"
    return settings.logging.level


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


def _load_settings_or_exit(config_path: str | None) -> Settings:
    """Load settings, translating common failure modes into clean errors.

    Returns Settings on success or terminates the process with a non-zero
    exit code on failure (FileNotFoundError, ValidationError).
    """
    try:
        return load_settings(config_path)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE_ERROR) from e
    except ValidationError as e:
        # Most common cause: GITHUB_TOKEN missing from env/.env.
        missing_token = any(
            err.get("loc") == ("github_token",) and err.get("type") == "missing"
            for err in e.errors()
        )
        if missing_token:
            print(
                "error: GITHUB_TOKEN is not set. Put it in .env or export it "
                "in your shell.",
                file=sys.stderr,
            )
        else:
            print(f"error: invalid configuration:\n{e}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE_ERROR) from e


def _emit_report(
    model: BaseModel,
    output_path: str,
    also_stdout: bool,
    indent: int,
    logger: logging.Logger,
) -> None:
    """Serialise a scan model to JSON and write it to file and/or stdout.

    ``output_path == "-"`` skips the file and prints to stdout; otherwise the
    file is written and stdout is used only when ``also_stdout`` is set.
    """
    json_text = json.dumps(
        model.model_dump(mode="json"), indent=indent, ensure_ascii=False
    )
    write_to_file = output_path != "-"
    if write_to_file:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_text, encoding="utf-8")
        logger.info("Wrote scan report to %s", out_path)
    if also_stdout or not write_to_file:
        print(json_text)


def main(argv: list[str] | None = None) -> int:
    arg_parser = _build_arg_parser()
    args = arg_parser.parse_args(argv)
    if args.path is not None:
        # stdout carries the report, and a working copy has only its own branch.
        if args.branch:
            arg_parser.error("--branch cannot be used with --path")
        if args.stdout or args.output == "-":
            arg_parser.error("--path prints the report to stdout; write JSON to a file")

    settings = _load_settings_or_exit(args.config)
    if args.path is not None:
        return _scan_local(args, settings)

    setup_logging(_resolve_log_level(settings, args.verbose, args.quiet))
    logger = logging.getLogger("gen-sdk-toolset")

    branch = args.branch or settings.github.branch
    output_path = args.output or settings.output.path
    try:
        scanner = build_scanner(settings)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    logger.info("Scanning repository %s@%s", args.repo, branch)
    repo_result = scanner.scan_repository(repo=args.repo, branch=branch)
    _emit_report(repo_result, output_path, args.stdout, settings.output.indent, logger)
    if repo_result.failure_message:
        logger.error("Repo scan reported an error: %s", repo_result.failure_message)
        return EXIT_RUNTIME_ERROR
    return EXIT_OK


def _scan_local(args: argparse.Namespace, settings: Settings) -> int:
    setup_logging(_resolve_log_level(settings, args.verbose, args.quiet))
    logger = logging.getLogger("gen-sdk-toolset")
    root = Path(args.path)
    try:
        scanner = build_local_scanner(settings, root)
        provider = scanner.doc_provider
        if not isinstance(provider, LocalDocProvider):  # pragma: no cover
            raise RuntimeError("build_local_scanner must wire a LocalDocProvider")
        branch = provider.current_branch()
        dirty = provider.has_uncommitted_changes(settings.scanner.api_ref_path)
    except LocalSourceError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    repo = provider.root.name
    logger.info("Scanning local working copy %s (%s)", provider.root, branch)
    repo_result = scanner.scan_repository(repo=repo, branch=branch)
    _emit_report(
        repo_result,
        args.output or settings.output.path,
        False,
        settings.output.indent,
        logger,
    )
    if repo_result.failure_message:
        logger.error("Repo scan reported an error: %s", repo_result.failure_message)
        return EXIT_RUNTIME_ERROR
    print(_local_report(repo_result, repo=repo, dirty=dirty, settings=settings))
    return EXIT_OK


def _local_report(
    result: RepositoryScanResult, *, repo: str, dirty: bool, settings: Settings
) -> str:
    if not isinstance(result.repository, Service) or not result.repository.documents:
        return (
            f"# API reference scan: {repo}\n\n"
            f"No API reference found under `{settings.scanner.api_ref_path}`.\n"
        )
    return render_markdown(
        find_doc_errors(result), repo=repo, commit=result.commit_hash, dirty=dirty
    )


if __name__ == "__main__":
    raise SystemExit(main())
