import json
import logging
import sys

from tools.config import get_settings
from tools.domain.services.scanner import ScannerService
from tools.infrastructure.github.client import GitHubDocProvider
from tools.infrastructure.parsers.doc_parser import DocutilsParser


def setup_logging(level: str):
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


def main():
    settings = get_settings()
    setup_logging(settings.log_level)

    logger = logging.getLogger("gen-sdk-toolset")
    logger.info("Starting organization scan...")

    github_provider = GitHubDocProvider(
        token=settings.github_token.get_secret_value(),
        api_url=settings.github_api_url,
        prefix=settings.rst_source_prefix,
    )
    rst_parser = DocutilsParser()
    scanner = ScannerService(doc_provider=github_provider, parser=rst_parser)

    result = scanner.scan_organization(
        org=settings.github_default_org,
        branch=settings.github_default_branch,
    )

    # Org-wide rollup of parsed documents by API version.
    by_version: dict[str, int] = {}
    for repo in result.repos:
        for version, docs in repo.documents_by_version.items():
            by_version[version] = by_version.get(version, 0) + len(docs)
    # Sort by count desc for at-a-glance reading.
    by_version = dict(sorted(by_version.items(), key=lambda kv: kv[1], reverse=True))

    # Full structured result as JSON-serializable dict on stdout for downstream tooling.
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
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    # Human-readable summary on stderr.
    logger.info("=" * 60)
    logger.info("Scan summary for org '%s'", result.org)
    logger.info("  Total repos discovered : %d", result.total_repos)
    logger.info("  Eligible (api-ref/source): %d", result.eligible_repos)
    logger.info("  Skipped repos          : %d", len(result.skipped_repos))
    logger.info("  Total API documents    : %d", result.total_documents)
    logger.info("  Successfully parsed    : %d", result.total_parsed)
    logger.info("  Failed to parse        : %d", result.total_failed)
    if by_version:
        logger.info("  Parsed by version      :")
        for version, count in by_version.items():
            logger.info("    - %-12s : %d", version, count)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
