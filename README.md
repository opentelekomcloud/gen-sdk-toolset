# gen-sdk-toolset

Automated Python SDK generation from Open Telekom Cloud (OTC) API documentation.

The current focus is the **repository scanner**: it walks the `opentelekomcloud-docs`
GitHub organisation, locates every repository whose docs contain an
`api-ref/source/` directory, parses each endpoint RST file, and emits a
structured JSON report describing which documents can be processed today and
which can't.

## Setup

```bash
git clone git@github.com:opentelekomcloud/gen-sdk-toolset.git
cd gen-sdk-toolset

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

The scanner reads its configuration from three sources, in order of precedence:

1. **CLI flags** (`--org`, `--branch`, `--output`, …)
2. **Environment variables**, including nested overrides via `__`
   (e.g. `GITHUB__ORG=foo`)
3. **`scan-config.toml`** in the current working directory, or a custom path
   via `--config <path>`

### GitHub token

The token is the one thing kept *outside* the TOML config — it lives in `.env`
(or your shell environment) so it can never be committed by accident.

1. Create a GitHub personal access token: **Settings → Developer settings →
   Personal access tokens → Tokens (classic)**. Scope: `public_repo`.
2. Copy it into `.env`:

   ```bash
   cp .env.example .env
   # then edit .env and set GITHUB_TOKEN=ghp_...
   ```

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

## Usage

```bash
# Scan with defaults from scan-config.toml; report written to scan-output.json
gen-sdk-scan

# Scan a different branch, write report to a custom path
gen-sdk-scan --branch develop --output reports/develop.json

# Print the report to stdout in addition to writing it
gen-sdk-scan --stdout

# Pipe-only output (no file written)
gen-sdk-scan --output - | jq '.summary'

# Use a non-default config file
gen-sdk-scan --config configs/staging.toml

# Verbose logging
gen-sdk-scan -v
```

### Command-line flags

| Flag | Effect |
|---|---|
| `--config PATH` | Path to TOML config (default: `scan-config.toml`) |
| `--output PATH` | Output JSON file path. `-` redirects to stdout instead |
| `--org NAME` | Override `[github].org` |
| `--branch NAME` | Override `[github].branch` |
| `--stdout` | Also print the JSON report to stdout (in addition to the file) |
| `-v`, `--verbose` | DEBUG-level logging |
| `-q`, `--quiet` | WARNING-level logging |

### Output

The scan produces a single JSON file structured as a *quality report*:

- **Per-document results** — for every endpoint doc encountered:
  - `document`, `repo`, `service`, `method`, `uri`, `title`, `api_version`
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
  - Computed fields: `overall_status` (`ok` / `partial` / `failed` /
    `unsupported`), `completeness` (0.0–1.0), `all_issues` (flat list
    aggregating gating + per-section issues)

- **Per-repo rollups** (`RepoScanResult`):
  - `documents`, `non_endpoint_documents`, `documents_by_version`,
    `total_documents`, `status_counts`

- **Org-level `quality_summary`** — the headline numbers:
  - `by_overall_status` — `{"ok": N, "partial": N, "failed": N, "unsupported": N}`
  - `by_section_status` — distribution per section
  - `top_issues` — most frequent issue codes across the org
  - plus `report_schema_version: 1`

## Development

```bash
pytest                  # 66 tests covering style/section classifiers,
                        # parser end-to-end on real OTC fixtures, scanner
ruff check src/         # lint
ruff format src/        # auto-format
```
