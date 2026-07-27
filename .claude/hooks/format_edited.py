"""PostToolUse hook: format and auto-fix the file that was just edited.

Keeps ruff's mechanical rules out of review entirely - by the time anyone reads
the diff, formatting and import order are already right.

Only touches Python files, only the one file that was edited, and never fails
the turn: a formatter that blocks work would just get switched off.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    raw = (payload.get("tool_input") or {}).get("file_path")
    if not raw:
        return

    path = Path(raw)
    if path.suffix != ".py" or not path.is_file():
        return
    if "migrations/versions/" in path.as_posix():
        return  # excluded from ruff in pyproject.toml

    for argv in (
        ["ruff", "format", str(path)],
        ["ruff", "check", "--fix", "--quiet", str(path)],
    ):
        try:
            subprocess.run(argv, capture_output=True, timeout=45)
        except (OSError, subprocess.SubprocessError):
            return


if __name__ == "__main__":
    main()
