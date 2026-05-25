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

The scan produces a single JSON file containing:

- per-document parse results (`document`, `method`, `uri`, `title`, `api_version`,
  parsed/failed status, error if failed)
- per-repo rollups (`total_documents`, `parsed_count`, `failed_count`,
  `documents_by_version`)
- an org-level `summary` block: total / eligible / skipped repo counts,
  total / parsed / failed document counts, parsed-by-version distribution

## Development

```bash
pytest                  # tests (incremental — currently bare framework)
ruff check src/         # lint
ruff format src/        # auto-format
```
