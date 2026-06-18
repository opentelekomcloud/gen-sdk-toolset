"""gen-sdk tooling package.

Exposes ``__version__``, single-sourced from the installed package metadata
(``pyproject.toml``) so the scanner can stamp every report with the parser
version that produced it. Downstream tooling uses it to tell "docs changed"
apart from "parser improved" between runs.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("gen-sdk-tooling")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
