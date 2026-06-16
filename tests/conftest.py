"""Shared test fixtures."""

from __future__ import annotations

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
