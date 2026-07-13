"""CLI entry point: scan an OTC docs organisation and emit a JSON report."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError

from tools.config import Settings, load_settings
from tools.domain.report import OrgScanResult
from tools.scanner.github.client import GitHubDocProvider
from tools.scanner.parsers import DocutilsParser, classify_doc_style
from tools.scanner.service import ScannerService
from tools.shared.exceptions import RepositoryError
from tools.shared.report import OverallStatus

# Exit codes
EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gen-sdk-scan",
        description=(
            "Scan an OTC documentation organisation and emit a JSON report "
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
    # Org-wide run (--org) and single-repo run (--repo) are mutually exclusive.
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--org",
        metavar="NAME",
        help="GitHub organisation to scan (org-wide run). Overrides [github].org.",
    )
    target.add_argument(
        "--repo",
        metavar="OWNER/NAME",
        help=(
            "Scan a single repository instead of the whole org. Emits one "
            "result in the same shape as an element of the org report's "
            "repos[]."
        ),
    )
    parser.add_argument(
        "--branch",
        metavar="NAME",
        help="Git branch to scan. Overrides [github].branch.",
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


def _build_scanner(settings: Settings) -> ScannerService:
    """Composition root: wire the adapters into a :class:`ScannerService`."""
    github_provider = GitHubDocProvider(
        token=settings.github_token.get_secret_value(),
        api_url=settings.github.api_url,
        prefix=settings.scanner.rst_source_prefix,
    )
    return ScannerService(
        doc_provider=github_provider,
        parser=DocutilsParser(),
        style_classifier=classify_doc_style,
        max_workers=settings.scanner.max_workers,
        api_ref_path=settings.scanner.api_ref_path,
        excluded_segments=settings.scanner.excluded_segments,
    )


def _print_human_summary(
    result: OrgScanResult, api_ref_path: str, logger: logging.Logger
) -> None:
    """Display-only roll-up on stderr. Reads the model's computed views."""
    status_counts = result.quality_summary.by_overall_status
    logger.info("=" * 60)
    logger.info("Scan summary for org '%s'", result.org)
    logger.info("  Total repos discovered : %d", result.total_repos)
    logger.info("  Eligible (%s)   : %d", api_ref_path, result.eligible_repos)
    logger.info("  Skipped repos          : %d", len(result.skipped_repos))
    logger.info("  Total API documents    : %d", result.total_documents)
    for status in OverallStatus:
        if status.value in status_counts:
            logger.info("  %-22s : %d", status.value, status_counts[status.value])
    if result.by_version:
        logger.info("  Parsed by version      :")
        for version, count in result.by_version.items():
            logger.info("    - %-12s : %d", version, count)
    top_issues = result.quality_summary.top_issues[:5]
    if top_issues:
        logger.info("  Top issues             :")
        for entry in top_issues:
            logger.info("    - %-26s : %d", entry["code"], entry["count"])
    logger.info("=" * 60)


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
    args = _build_arg_parser().parse_args(argv)

    settings = _load_settings_or_exit(args.config)
    setup_logging(_resolve_log_level(settings, args.verbose, args.quiet))
    logger = logging.getLogger("gen-sdk-toolset")

    branch = args.branch or settings.github.branch
    output_path = args.output or settings.output.path
    scanner = _build_scanner(settings)

    # Single-repo mode: scan one repo → one repos[]-shaped RepoScanResult.
    if args.repo:
        logger.info("Scanning repository %s@%s", args.repo, branch)
        repo_result = scanner.find_endpoints(repo=args.repo, branch=branch)
        _emit_report(
            repo_result, output_path, args.stdout, settings.output.indent, logger
        )
        if repo_result.error:
            logger.error("Repo scan reported an error: %s", repo_result.error)
            return EXIT_RUNTIME_ERROR
        return EXIT_OK

    # Org-wide mode (default).
    org = args.org or settings.github.org
    logger.info("Starting organization scan for %s@%s", org, branch)
    try:
        result = scanner.scan_organization(org=org, branch=branch)
    except RepositoryError as e:
        # Org-level failures (auth, rate limit, network) surface as a clean
        # message rather than a traceback. Per-document errors are handled
        # inside the scanner and recorded in the report.
        logger.error("Scan aborted: %s", e)
        return EXIT_RUNTIME_ERROR

    _emit_report(result, output_path, args.stdout, settings.output.indent, logger)
    _print_human_summary(result, settings.scanner.api_ref_path, logger)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
