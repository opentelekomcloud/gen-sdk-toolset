"""Scan a documentation repository from a local working copy."""

from .provider import LocalDocProvider, LocalSourceError

__all__ = ["LocalDocProvider", "LocalSourceError"]
