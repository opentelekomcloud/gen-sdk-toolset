"""Composition root: wire the scanner adapters into a :class:`ScannerService`."""

from __future__ import annotations

from tools.config import Settings, require_github_token
from tools.scanner.github.client import GitHubDocProvider
from tools.scanner.parsers import DocutilsParser, classify_doc_style
from tools.scanner.service import ScannerService


def build_doc_provider(settings: Settings) -> GitHubDocProvider:
    """Build the GitHub provider on its own.

    Repository discovery needs the provider without a parser or a scanner, so
    the wiring lives here rather than being reached through a ScannerService.
    """
    return GitHubDocProvider(
        token=require_github_token(settings).get_secret_value(),
        api_url=settings.github.api_url,
        prefix=settings.scanner.rst_source_prefix,
    )


def build_scanner(settings: Settings) -> ScannerService:
    """Wire the GitHub provider and parser into a :class:`ScannerService`."""
    return ScannerService(
        doc_provider=build_doc_provider(settings),
        parser=DocutilsParser(),
        style_classifier=classify_doc_style,
        max_workers=settings.scanner.max_workers,
        api_ref_path=settings.scanner.api_ref_path,
        excluded_segments=settings.scanner.excluded_segments,
    )
