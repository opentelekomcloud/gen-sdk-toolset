"""Module entry point so the CLI can be run as ``python -m tools.scanner``."""

from __future__ import annotations

from tools.scanner.main import main

if __name__ == "__main__":
    raise SystemExit(main())
