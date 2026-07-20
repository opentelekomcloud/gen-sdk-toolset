"""Regression checks for the committed real-repository scan example."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tools.shared.ir import Endpoint, Service
from tools.shared.scan import RepositoryScanResult

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "examples" / "repo_scan_example.json"
)
FULL_SHA = re.compile(r"[0-9a-f]{40}")


def test_repo_scan_example_is_a_complete_scan_snapshot() -> None:
    payload = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    result = RepositoryScanResult.model_validate(payload)

    assert result.model_dump(mode="json") == payload
    assert FULL_SHA.fullmatch(result.branch)
    assert result.commit_hash == result.branch
    assert isinstance(result.repository, Service)
    assert result.repository.documents
    assert "non_endpoint_documents" not in payload
    assert "document_results" not in payload
    assert "section_results" not in payload
    assert "endpoint_path" not in EXAMPLE_PATH.read_text(encoding="utf-8")
    assert all(document.title for document in result.repository.documents)
    assert any(
        not isinstance(document, Endpoint)
        and document.scan_result.failure_reason is None
        for document in result.repository.documents
    )
