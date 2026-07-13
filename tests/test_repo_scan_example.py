"""Regression checks for the committed real-repository scan example."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tools.shared.report import RepoScanResult

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "examples" / "repo_scan_example.json"
)
FULL_SHA = re.compile(r"[0-9a-f]{40}")


def test_repo_scan_example_matches_current_contract_exactly() -> None:
    payload = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))

    result = RepoScanResult.model_validate(payload)

    assert result.model_dump(mode="json") == payload
    assert FULL_SHA.fullmatch(payload["branch"])
    assert payload["commit_hash"] == payload["branch"]
