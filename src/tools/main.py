"""CLI entry point: scan an OTC docs organisation and emit a JSON report."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from tools.config import Settings, load_settings
from tools.domain.exceptions import RepositoryError
from tools.domain.services.scanner import ScannerService
from tools.infrastructure.github.client import GitHubDocProvider
from tools.infrastructure.parsers.doc_parser import DocutilsParser

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
    parser.add_argument(
        "--org",
        metavar="NAME",
        help="GitHub organisation to scan. Overrides [github].org.",
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


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    settings = _load_settings_or_exit(args.config)
    setup_logging(_resolve_log_level(settings, args.verbose, args.quiet))
    logger = logging.getLogger("gen-sdk-toolset")

    # CLI overrides for top-level settings
    org = args.org or settings.github.org
    branch = args.branch or settings.github.branch
    output_path = args.output or settings.output.path
    write_to_file = output_path != "-"

    logger.info("Starting organization scan for %s@%s", org, branch)

    github_provider = GitHubDocProvider(
        token=settings.github_token.get_secret_value(),
        api_url=settings.github.api_url,
        prefix=settings.scanner.rst_source_prefix,
    )
    rst_parser = DocutilsParser()
    scanner = ScannerService(
        doc_provider=github_provider,
        parser=rst_parser,
        max_workers=settings.scanner.max_workers,
        excluded_segments=settings.scanner.excluded_segments,
    )

    try:
        result = scanner.scan_organization(
            org=org,
            branch=branch,
            api_ref_path=settings.scanner.api_ref_path,
        )
    except RepositoryError as e:
        # Org-level failures (auth, rate limit, network) surface as a clean
        # message rather than a traceback. Per-document errors are handled
        # inside the scanner and recorded in the report.
        logger.error("Scan aborted: %s", e)
        return EXIT_RUNTIME_ERROR

    # Org-wide rollup of parsed documents by API version.
    by_version: dict[str, int] = {}
    for repo in result.repos:
        for version, docs in repo.documents_by_version.items():
            by_version[version] = by_version.get(version, 0) + len(docs)
    by_version = dict(sorted(by_version.items(), key=lambda kv: kv[1], reverse=True))

    # JSON-serialisable payload with a summary block at the top level.
    payload = result.model_dump(mode="json")
    payload["summary"] = {
        "total_repos": result.total_repos,
        "eligible_repos": result.eligible_repos,
        "skipped_repos": len(result.skipped_repos),
        "total_documents": result.total_documents,
        "parsed": result.total_parsed,
        "failed": result.total_failed,
        "by_version": by_version,
    }

    json_text = json.dumps(payload, indent=settings.output.indent, ensure_ascii=False)

    if write_to_file:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_text, encoding="utf-8")
        logger.info("Wrote scan report to %s", out_path)

    if args.stdout or not write_to_file:
        print(json_text)

    # Human-readable summary on stderr.
    logger.info("=" * 60)
    logger.info("Scan summary for org '%s'", result.org)
    logger.info("  Total repos discovered : %d", result.total_repos)
    logger.info(
        "  Eligible (%s)   : %d", settings.scanner.api_ref_path, result.eligible_repos
    )
    logger.info("  Skipped repos          : %d", len(result.skipped_repos))
    logger.info("  Total API documents    : %d", result.total_documents)
    logger.info("  Successfully parsed    : %d", result.total_parsed)
    logger.info("  Failed to parse        : %d", result.total_failed)
    if by_version:
        logger.info("  Parsed by version      :")
        for version, count in by_version.items():
            logger.info("    - %-12s : %d", version, count)
    logger.info("=" * 60)

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
