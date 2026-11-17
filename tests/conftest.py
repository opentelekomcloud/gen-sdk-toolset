"""Shared test fixtures."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Return the contents of `tests/fixtures/<name>`."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def cce_doc() -> str:
    return load_fixture("style_a_cce_grid.rst")


@pytest.fixture
def vpc_doc() -> str:
    return load_fixture("style_a_vpc_with_refs.rst")


@pytest.fixture
def kms_doc() -> str:
    return load_fixture("style_a_kms_simple_table.rst")


@pytest.fixture
def iam_doc() -> str:
    return load_fixture("style_a_iam_ref_in_param.rst")


@pytest.fixture
def obs_doc() -> str:
    return load_fixture("style_b_obs.rst")


@pytest.fixture
def elb_list_doc() -> str:
    return load_fixture("style_a_elb_list_query.rst")


@pytest.fixture
def two_body_tables_doc() -> str:
    return load_fixture("style_a_two_body_tables.rst")


@pytest.fixture
def anti_ddos_root_doc() -> str:
    return load_fixture("style_a_anti_ddos_root_endpoint.rst")


@pytest.fixture
def anti_ddos_legacy_uri_doc() -> str:
    return load_fixture("style_a_anti_ddos_legacy_uri.rst")


@pytest.fixture
def anti_ddos_get_request_doc() -> str:
    return load_fixture("style_a_anti_ddos_get_request.rst")


@pytest.fixture
def anti_ddos_direct_response_doc() -> str:
    return load_fixture("style_a_anti_ddos_direct_response.rst")


@pytest.fixture
def cce_inline_examples_doc() -> str:
    return load_fixture("style_a_cce_inline_examples.rst")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            *args,
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def make_git_repo(tmp_path: Path):
    """Create a committed git working copy from ``{relative path: content}``."""

    def _make(files: dict[str, str], name: str = "docs-repo") -> Path:
        root = tmp_path / name
        root.mkdir()
        for relative, content in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        _git(root, "init", "-q", "-b", "main")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "--allow-empty", "-m", "init")
        return root

    return _make
