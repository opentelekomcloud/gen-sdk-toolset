"""Scan an OTC docs repo and classify RST files: endpoint vs non-endpoint.

Usage:
    python scanner.py opentelekomcloud-docs/cloud-container-engine
"""

from __future__ import annotations

import argparse
import base64
import re
import sys

import requests

from ..config import get_settings


URI_RE = re.compile(
    r"^\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/\S+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def make_session() -> requests.Session:
    settings = get_settings()
    s = requests.Session()
    s.headers["Accept"] = "application/vnd.github+json"
    s.headers["Authorization"] = f"Bearer {settings.github_token.get_secret_value()}"
    return s


def list_rst_paths(session: requests.Session, repo: str, branch: str) -> list[str]:
    """Get all .rst file paths under api-ref/source/ (one API call)."""
    settings = get_settings()
    url = f"{settings.github_api_url}/repos/{repo}/git/trees/{branch}?recursive=1"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return [
        item["path"]
        for item in resp.json().get("tree", [])
        if item["path"].startswith(settings.rst_source_prefix)
        and item["path"].endswith(".rst")
    ]


def fetch_content(session: requests.Session, repo: str, path: str) -> str:
    """Fetch raw file content (one API call per file)."""
    settings = get_settings()
    url = f"{settings.github_api_url}/repos/{repo}/contents/{path}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return base64.b64decode(resp.json()["content"]).decode("utf-8")


def has_uri(content: str) -> re.Match | None:
    """Check if RST content contains an HTTP method + path line."""
    return URI_RE.search(content)


def scan(repo: str, branch: str) -> None:
    session = make_session()

    paths = list_rst_paths(session, repo, branch)
    print(f"Found {len(paths)} RST files in {repo}\n")

    endpoints: list[tuple[str, str, str]] = []  # (path, method, uri)
    skipped: list[str] = []

    for i, path in enumerate(paths, 1):
        sys.stdout.write(f"\r  Checking [{i}/{len(paths)}] ...")
        sys.stdout.flush()

        content = fetch_content(session, repo, path)
        match = has_uri(content)
        if match:
            endpoints.append((path, match.group(1).upper(), match.group(2)))
        else:
            skipped.append(path)

    print(f"\n\n{'=' * 60}")
    print(f"ENDPOINTS ({len(endpoints)}):")
    print(f"{'=' * 60}")
    for path, method, uri in endpoints:
        print(f"  {method:7s} {uri}")
        print(f"          {path}")

    print(f"\n{'=' * 60}")
    print(f"SKIPPED ({len(skipped)}):")
    print(f"{'=' * 60}")
    for path in skipped:
        print(f"  {path}")


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Scan OTC docs repo for API endpoints")
    parser.add_argument(
        "repo",
        nargs="?",
        default=f"{settings.github_default_org}/cloud-container-engine",
        help="Repository in owner/name format",
    )
    parser.add_argument(
        "--branch",
        default=settings.github_default_branch,
    )
    args = parser.parse_args()

    scan(args.repo, args.branch)


if __name__ == "__main__":
    main()