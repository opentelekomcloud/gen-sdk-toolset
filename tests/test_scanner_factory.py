"""Smoke test for the scanner composition root (``build_scanner``).

The CLI and panel tests monkeypatch ``build_scanner`` out, so this is the one
place the factory body actually executes: a constructor-signature drift in the
wired adapters fails here instead of in a real scan.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("pydantic_settings")
pytest.importorskip("requests")
pytest.importorskip("docutils")

from tools.config import Settings  # noqa: E402
from tools.scanner.factory import build_scanner  # noqa: E402
from tools.scanner.github.client import GitHubDocProvider  # noqa: E402
from tools.scanner.parsers import DocutilsParser, classify_doc_style  # noqa: E402
from tools.scanner.service import ScannerService  # noqa: E402


def test_build_scanner_wires_service_from_settings():
    settings = Settings(github_token="test-token")

    scanner = build_scanner(settings)

    assert isinstance(scanner, ScannerService)
    assert isinstance(scanner.doc_provider, GitHubDocProvider)
    assert scanner.doc_provider.api_url == settings.github.api_url
    assert scanner.doc_provider.prefix == settings.scanner.rst_source_prefix
    assert scanner.doc_provider.session.headers["Authorization"] == "Bearer test-token"
    assert isinstance(scanner.parser, DocutilsParser)
    assert scanner.style_classifier is classify_doc_style
    assert scanner.max_workers == settings.scanner.max_workers
    assert scanner.api_ref_path == settings.scanner.api_ref_path.rstrip("/")
    assert scanner.excluded_segments == frozenset(settings.scanner.excluded_segments)


def test_build_scanner_requires_github_token():
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        build_scanner(Settings(github_token=None))
