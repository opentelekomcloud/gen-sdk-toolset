from gen_sdk_tooling.infrastructure.github.client import GitHubDocProvider
from gen_sdk_tooling.domain.services.scanner import ScannerService
from gen_sdk_tooling.config import get_settings
from gen_sdk_tooling.infrastructure.parsers.doc_parser import DocutilsParser
import logging
import sys


def setup_logging(level: str):
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def main():
    settings = get_settings()
    setup_logging(settings.log_level)

    logger = logging.getLogger("gen_sdk_tooling")
    logger.info("Starting tool...")

    github_provider = GitHubDocProvider(
        token=settings.github_token.get_secret_value(),
        api_url=settings.github_api_url,
        prefix=settings.rst_source_prefix
    )

    rst_parser = DocutilsParser()

    scanner = ScannerService(doc_provider=github_provider, parser=rst_parser)

    service = scanner.find_endpoints(
        repo="opentelekomcloud-docs/cloud-container-engine",
        branch="main"
    )

    for ep in service.endpoints:
        print(f"Found: {ep.method} {ep.path}")


if __name__ == "__main__":
    main()
