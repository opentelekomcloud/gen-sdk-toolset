"""Composition root: wire the scanner adapters into a :class:`ScannerService`.

Extracted from ``scanner/main.py`` so both the CLI and the panel background
job runner build a scanner the same way.
"""

from __future__ import annotations

from tools.config import Settings, require_github_token
from tools.scanner.github.client import GitHubDocProvider
from tools.scanner.parsers import DocutilsParser, classify_doc_style
from tools.scanner.service import ScannerService


def build_scanner(settings: Settings) -> ScannerService:
    """Wire the GitHub provider and parser into a :class:`ScannerService`."""
    github_provider = GitHubDocProvider(
        token=require_github_token(settings).get_secret_value(),
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
