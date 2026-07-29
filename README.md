# gen-sdk-toolset

Automated Python SDK generation from Open Telekom Cloud (OTC) API documentation.

The current focus is the **repository scanner**: given one `opentelekomcloud-docs`
repository, it checks that the repo's docs contain an `api-ref/source/`
directory, parses each endpoint RST file, and emits a structured JSON result
describing which documents can be processed today and which can't. Scanning a
whole organization — and aggregating the results into headline numbers — is
the panel's job, not the scanner's.

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

1. **CLI flags** (`--repo`, `--branch`, `--output`, …)
2. **Environment variables**, including nested overrides via `__`
   (e.g. `GITHUB__ORG=foo`)
3. **`scan-config.toml`** in the current working directory, or a custom path
   via `--config <path>`

The supported entrypoint is `uv run gen-sdk-scan`, which scans exactly one
repository per run:

```bash
# Scan one repository and print one raw RepositoryScanResult (no file written)
uv run gen-sdk-scan \
  --repo opentelekomcloud-docs/anti-ddos \
  --output -

# A branch name or a fixed commit SHA can select the snapshot
uv run gen-sdk-scan \
  --repo opentelekomcloud-docs/anti-ddos \
  --branch 8ff5254f6b7d669170bdacbdf5058e9adcfbe75f \
  --output reports/anti-ddos.json

# Write to a file and also print the same JSON to stdout
uv run gen-sdk-scan --repo OWNER/NAME --output report.json --stdout

# Use a non-default config file or enable verbose logging
uv run gen-sdk-scan --repo OWNER/NAME --config configs/staging.toml -v
```

`--repo` is required and takes an `OWNER/NAME` slug. Scanning a whole
organization is the panel's job, not the CLI's: it needs durable job state to
resume after a rate limit, which a one-shot command cannot provide.

When the configured API reference path is absent, the scan succeeds with an
empty result whose `repository` remains a plain `Repository`. A repository or
ref that cannot be confirmed instead includes a diagnostic `error` and exits
non-zero.

### Command-line flags

| Flag | Effect |
|---|---|
| `--config PATH` | Path to TOML config (default: `scan-config.toml`) |
| `--output PATH` | Output JSON file path. `-` redirects to stdout instead |
| `--repo OWNER/NAME` | **Required.** Repository to scan; emits one `RepositoryScanResult` |
| `--branch NAME` | Branch name or fixed commit SHA to scan |
| `--stdout` | Also print the JSON report to stdout (in addition to the file) |
| `-v`, `--verbose` | DEBUG-level logging |
| `-q`, `--quiet` | WARNING-level logging |

### Output

A run produces one raw `RepositoryScanResult`, carrying **data only**: derived
views (per-document overall status, flat issue lists, version and quality
roll-ups) are not embedded in the JSON. They are computed by the pure functions
in `tools.panel.core.analytics`, so every number the panel reports has exactly
one definition and cannot drift from a second stored copy.

- **Repository data** is represented by `Repository` or its eligible
  specialization `Service`. A service contains `Document` records; recognized
  endpoint documents are represented by `Endpoint(Document)` and contain
  their extracted `Section` records. The `kind` discriminator identifies each
  polymorphic entity as `repository`, `service`, `document`, or `endpoint`.
  A plain `Document` without a failure is a successfully scanned non-endpoint;
  this classification is derived from the entity and is not stored in a
  parallel `non_endpoint_documents` field.

- **Scan results** are nested into the entities produced by that scan:
  - every document carries one `DocumentScanResult` in `scan_result`;
  - every endpoint section carries one `SectionScanResult` in `scan_result`;
  - result payloads contain diagnostics only and do not repeat their document
    or section;
  - section ownership is expressed by nesting, so sections do not repeat an
    `endpoint_path` foreign key in the JSON snapshot.

- **Repository scan metadata**:
  - `branch`, `commit_hash`, and `scanner_version` identify the scan;
  - API-version counts are derived from `Service.endpoints`, not stored in a
    parallel `documents_by_version` structure;
  - `error` — repo-level failure (e.g. file listing failed, or a truncated
    file tree, so a partial scan is never mistaken for a clean one)

- **Derived views** (`tools.panel.core.analytics`, computed by the panel —
  never stored in the scan result):
  - `quality.py` — the per-document primitives: `document_sections` and
    `doc_all_issues` (every diagnostic flattened, with section-prefixed
    locations), plus the `OverallStatus` vocabulary
  - `generation.py` — the roll-ups a scan is persisted with: `document_status`
    per document, and `analyze_generation` for the headline numbers
    (`GenerationAnalytics`: status counters, `by_section_status`,
    `issues_by_code`, `by_version`, completeness)

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

Working on the code itself is documented separately, so it stays in one place:

- [CONTRIBUTING.md](CONTRIBUTING.md) — branches, commits, pull requests, CI gates
- [AGENTS.md](AGENTS.md) — the full command reference (lint, tests, coverage,
  schema regeneration) and the project layout
- [docs/FAQ.md](docs/FAQ.md) — how to carry out the common development tasks
- [docs/AGENT-TOOLING.md](docs/AGENT-TOOLING.md) — the `/plan`, `/review` and
  `/pr` commands, the review agents, and the hooks that apply themselves
- [STYLEGUIDE.md](STYLEGUIDE.md) — code conventions
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — the canonical domain vocabulary
