# gen-sdk-toolset

Automated Python SDK generation from Open Telekom Cloud (OTC) API documentation.

The current focus is the **repository scanner**: it walks the `opentelekomcloud-docs`
GitHub organisation, locates every repository whose docs contain an
`api-ref/source/` directory, parses each endpoint RST file, and emits a
structured JSON report describing which documents can be processed today and
which can't.

## GitHub token

The token is the one thing kept *outside* the TOML config — it lives in `.env`
(or your shell environment) so it can never be committed by accident.

1. Create a GitHub personal access token: **Settings → Developer settings →
   Personal access tokens → Tokens (classic)**. Scope: `public_repo`.
2. Copy it into `.env`:

   ```bash
   cp .env.example .env
   # then edit .env and set GITHUB_TOKEN=ghp_...
   ```
   
## Panel

The panel is a web app over the scan results: a FastAPI backend and a
React + TypeScript frontend, living in `src/tools/panel/` and `frontend/`.

### Running the full stack (Docker)

Requires Docker Desktop running and a `.env` file in the repo root with
`GITHUB_TOKEN` set (the backend won't start without it).

From the repo root:

```bash
docker compose up --build
```

Starts both services:

- Backend (FastAPI) on `http://localhost:8000`
- Frontend (Vite) on `http://localhost:5173`

Stop with:

```bash
docker compose down
```

### Component docs

- Backend details: `src/tools/panel/README.md`
- Frontend dev (run without Docker): `frontend/README.md`

## Scanner Usage

### Setup

```bash
git clone git@github.com:opentelekomcloud/gen-sdk-toolset.git
cd gen-sdk-toolset
uv sync --extra dev
```

### Configuration

The scanner reads its configuration from three sources, in order of precedence:

1. **CLI flags** (`--org`, `--branch`, `--output`, …)
2. **Environment variables**, including nested overrides via `__`
   (e.g. `GITHUB__ORG=foo`)
3. **`scan-config.toml`** in the current working directory, or a custom path
   via `--config <path>`

The supported entrypoint is `uv run gen-sdk-scan`. Choose one target mode:

```bash
# Scan one repository and print one raw RepoScanResult (no file written)
uv run gen-sdk-scan \
  --repo opentelekomcloud-docs/anti-ddos \
  --output -

# A branch name or a fixed commit SHA can select the snapshot
uv run gen-sdk-scan \
  --repo opentelekomcloud-docs/anti-ddos \
  --branch 8ff5254f6b7d669170bdacbdf5058e9adcfbe75f \
  --output reports/anti-ddos.json

# Run the legacy organization scan
uv run gen-sdk-scan \
  --org opentelekomcloud-docs \
  --output reports/organization.json

# Write to a file and also print the same JSON to stdout
uv run gen-sdk-scan --repo OWNER/NAME --output report.json --stdout

# Use a non-default config file or enable verbose logging
uv run gen-sdk-scan --config configs/staging.toml -v
```

`--repo` requires exactly two non-empty components in `OWNER/NAME` form.
`--repo` and `--org` are mutually exclusive. A repository without the
configured API reference path is a normal, successful result with
`has_api_ref=false` and empty document collections; a repository or ref that
cannot be confirmed instead includes a diagnostic `error` and exits non-zero.

### Command-line flags

| Flag | Effect |
|---|---|
| `--config PATH` | Path to TOML config (default: `scan-config.toml`) |
| `--output PATH` | Output JSON file path. `-` redirects to stdout instead |
| `--repo OWNER/NAME` | Scan one repository and emit one `RepoScanResult` |
| `--org NAME` | Run the legacy organization scan; mutually exclusive with `--repo` |
| `--branch NAME` | Branch name or fixed commit SHA to scan |
| `--stdout` | Also print the JSON report to stdout (in addition to the file) |
| `-v`, `--verbose` | DEBUG-level logging |
| `-q`, `--quiet` | WARNING-level logging |

### Output

Repository mode produces one raw `RepoScanResult`. Legacy organization mode
produces a quality report (`report_schema_version: 5`) containing repository
results. Since schema v5 both forms carry **data only**: derived views
(per-document overall status, completeness, flat issue lists) are no longer
embedded in the JSON — they are computed by the pure functions in
`tools.domain.report.analytics`.

- **Per-document results** (`DocumentScanResult`) — for every endpoint
  doc encountered:
  - `document`, `repo`, `method`, `uri`, `title`, `api_version`
  - `failure_reason: Issue | null` — populated for gating failures (fetch
    failed, no URI line found, unsupported doc style)
  - `sections: dict[str, SectionResult]` — keyed by `path_params`,
    `query_params`, `headers`, `body`, `response`, `example_request`,
    `example_response`, `nested_objects`. Each section carries:
    - `status` — `ok` / `partial` / `failed` / `missing` / `skipped`
    - `issues` — structured `[{code, location, details}]` entries
    - `parameters` — extracted `Parameter` objects
    - `examples` — extracted `ExampleBlock` objects (raw text +
      best-effort JSON parse)
    - field-level metrics: `fields_total`, `fields_recognized`,
      `fields_unknown_type`, `fields_failed`

- **Per-repo results** (`RepoScanResult`):
  - `repo`, `branch`, `commit_hash` (head commit the scan saw),
    `has_api_ref`, `scanner_version`
  - `documents`, `non_endpoint_documents`, `excluded_documents`,
    `documents_by_version`
  - `incomplete` / `incomplete_reason` — set when the provider returned a
    truncated file tree, so a partial scan is never mistaken for a clean one
  - `error` — repo-level failure (e.g. file listing failed)

- **Org-level** (`OrgScanResult`, top of the file):
  - `report_schema_version`, `scanner_version`, `org`, `branch`,
    `total_repos`, `eligible_repos`, `skipped_repos`
  - computed roll-ups: `total_documents`, `by_version`, and
    `quality_summary` — the headline numbers:
    - `by_overall_status` — `{"ok": N, "partial": N, "failed": N, "unsupported": N}`
    - `by_section_status` — distribution per section
    - `top_issues` — most frequent issue codes across the org

### `scan-config.toml`

A committed default file with sensible values. Edit it (or override
individual fields via env / CLI) to tweak:

```toml
[github]
org = "opentelekomcloud-docs"
branch = "main"

[scanner]
rst_source_prefix = "api-ref/source/"
api_ref_path = "api-ref/source"
excluded_segments = ["out-of-date_apis"]
max_workers = 8

[output]
path = "scan-output.json"
indent = 2

[logging]
level = "INFO"
```

## Development

```bash
pytest                  # style/section classifiers, parser end-to-end on
                        # real OTC fixtures, scanner service, GitHub client
ruff check src/         # lint
ruff format src/        # auto-format
```
