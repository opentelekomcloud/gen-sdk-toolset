# SDK Generation Pipeline

> **Status:** draft for discussion

## Purpose

This document describes how `gen-sdk-tooling` produces Python SDK services
for T Cloud from upstream RST documentation. It covers the
component layout, the pipeline of operations, the infrastructure each
component depends on, and the phased rollout plan.

The architecture of the SDK output itself (file layout, contracts, conventions)
is defined in `python-t-cloud/docs/new_arch.md`. This document is about how
that output is *produced*, not what it looks like.

## Goals

- Automate Python SDK generation for services from upstream RST
  documentation hosted in `opentelekomcloud-docs/*`.
- Minimize manual work. Human involvement is concentrated at PR review,
  not at generation time.
- Continuous synchronization between docs and SDK once a service is generated.
- Predictable, debuggable output. A maintainer reading generated code six
  months from now can trace each fragment back to its source (template
  vs. LLM, which docs revision, which RST file).

## Non-goals

- **100% automation.** Human review of generated PRs is intentional and
  permanent, not a temporary measure.
- **Hand-editing generated files.** Files produced by the generator carry
  an auto-generated marker; hand-edits are not preserved across regeneration.
- **Runtime LLM.** LLMs are involved only at generation time. The shipped
  SDK contains deterministic Python with no LLM dependency.

## Component layout

`gen-sdk-tooling` is a single repository with four modules sharing a common
type layer. Each module is independent: it depends only on `shared/`, never
on its peers.

```
gen-sdk-tooling/
└── src/tools/
    ├── shared/        # IR, IssueCode, SectionResult, exceptions — type contracts
    ├── scanner/       # RST → IR + ScanReport
    ├── generator/     # IR → Python files (via Jinja2)
    └── llm/           # FIXME placeholders → resolved (via Ollama)
```

### Dependency rules

- `shared/` depends only on external libraries (pydantic, etc.).
- `scanner/`, `generator/`, `llm/` depend on `shared/` and external libraries.
  **They do not depend on each other.**
- There is no Python orchestrator. The pipeline is composed at the
  workflow level by GitHub Actions.

### What lives in `shared/`

- **IR models** (`Endpoint`, `Parameter`, nested object structures)
- **Report models** (`SectionResult`, `SectionStatus`, `IssueCode`,
  `DocumentScanResult`, `RepoScanResult`, `OrgScanResult`)
- **Exception hierarchy** (`GenSdkError`, `RepositoryError`, etc.)
- **Common enums** (`HttpMethod`, `ParameterType`)

`shared/` contains type contracts only. No business logic.

### What lives in each module

Each module ships a CLI entry point registered in `pyproject.toml`:

```toml
[project.scripts]
gen-sdk-scan = "tools.scanner.__main__:main"
gen-sdk-generate = "tools.generator.__main__:main"
gen-sdk-refine = "tools.llm.__main__:main"
```

This allows each module to run independently — useful for debugging, local
development, and as discrete steps in a GitHub Actions workflow.

## Pipeline composition

GitHub Actions composes the pipeline by running module CLIs in sequence,
passing data through the filesystem as artifacts:

```
┌──────────────────────────────────┐
│ 1. Fetch docs repo (actions/     │
│    checkout)                     │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│ 2. gen-sdk-scan                  │
│    output: ir.json, report.json  │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│ 3. Gating check (script reads    │
│    report.json, decides if       │
│    service is generatable)       │
└────────────────┬─────────────────┘
                 ▼ pass
┌──────────────────────────────────┐
│ 4. gen-sdk-generate              │
│    input:  ir.json, templates/   │
│    checkout python-t-cloud→/tmp, │
│    commit+push, open PR per repo │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│ 5. Automatic checks              │
│    (syntax, imports, ruff, mypy, │
│    FIXME count sanity)           │
└────────────────┬─────────────────┘
                 ▼ pass
┌──────────────────────────────────┐
│ 6. Commit 1 (Jinja baseline)     │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│ 7. gen-sdk-refine                │
│    input:  generated/, ir.json   │
│    output: refined/*.py          │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│ 8. Commit 2 (LLM refinement)     │
│    (skipped if LLM unavailable)  │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│ 9. Push branch, open PR          │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│ 10. CI on PR                     │
│     ruff/black, mypy, tests,     │
│     SonarCloud quality gate      │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│ 11. Notify Element/Matrix room   │
└──────────────────────────────────┘
```

Every step is a workflow step. Failures are visible per-step in the Actions
UI. Intermediate outputs (ir.json, generated/, refined/) are uploaded as
artifacts for post-mortem debugging.

### Why GitHub Actions for the generation pipeline

This covers the generation pipeline only; scan orchestration and state live in
the panel (see Components → Panel).

- Each module's natural output (JSON for scanner, Python files for generator
  and llm) is already a filesystem artifact. No special serialization is
  needed.
- Per-step visibility in the Actions UI shows exactly where failures happen
  without log diving.
- Re-running an individual failed step (e.g. LLM) is one click; the prior
  steps' outputs are preserved as artifacts.
- Additional checks (syntax, lint, SonarCloud) integrate naturally as
  separate workflow steps without entangling Python code.
- For local development, a thin shell script (`scripts/run-pipeline.sh`)
  replicates the workflow without introducing Python orchestration logic.

## Triggers

### Initial generation

- **Mechanism:** `workflow_dispatch` on
  `gen-sdk-tooling/.github/workflows/generate-service.yml`
- **Inputs:**
  - `docs_repo` — e.g. `opentelekomcloud-docs/cloud-container-engine`
  - `service_name` — destination service identifier in `python-t-cloud`
  - `dry_run_after_jinja` *(optional, default false)* — when true, the
    workflow stops after step 6 and uploads the Jinja-only output as an
    artifact for inspection. Used for template debugging, not in regular runs.
- **Initiator:** team members with write access to `gen-sdk-tooling`.
- **Entry points:**
  - GitHub UI: Actions tab → "Generate Service" → "Run workflow"
  - `gh CLI`: `gh workflow run generate-service.yml -f docs_repo=... -f service_name=...`

#### Why GitHub Actions, not chat bots or custom services

- No infrastructure to maintain (no bot hosting, no message queue, no RBAC layer).
- Built-in audit trail: who triggered, when, with which inputs.
- Long-running operations natively supported.
- Re-run is one click; parameter history preserved.
- Permissions align with repository access; no custom permission layer.
- Generated output (a PR) lives in GitHub anyway — trigger and result share
  the same surface.

### Maintenance

Maintenance is handled in v3 (see [Rollout phases](#rollout-phases)). It is
substantially more complex than initial generation because of the need for
incremental regeneration and output stability. The MVP and v2 do not include
maintenance — a documentation change requires a fresh manual trigger.

### Notifications

- **Trigger:** end of each workflow run that produces a PR.
- **Channel:** team's Element/Matrix room.
- **Content:** service name, PR link, brief stats (FIXMEs remaining, quality
  gate status).
- **Rationale:** GitHub Actions email notifications are author-scoped only;
  team-wide visibility for generated PRs requires explicit broadcast. Element
  is the team's existing coordination channel.
- **Implementation:** Matrix webhook call from the final workflow step.

## Components

### Scanner

Produces two outputs from RST:

- **IR** (`ir.json`) — the data the generator consumes (`Endpoint`,
  `Parameter`, nested objects).
- **ScanReport** (`report.json`) — metadata about parsing quality
  (`SectionResult` per section, with `IssueCode` for problems found).

The scanner does not generate code. It parses and reports.

Detailed scanner internals and the `SectionResult` / `IssueCode` model are
covered in a separate design issue in `gen-sdk-tooling`.

### Panel (control plane)

The panel is a stateful FastAPI + React app that drives scanning and is the
analytics surface. It exists because GitHub Actions can't: GitHub rate limits
prevent scanning all ~90 services in one pass, so services are scanned one at
a time and accumulated in a database.

- **Per-service scan orchestration** — triggers a single-repo scan (via the
  scanner's single-repo entrypoint), stores the result as a new generation.
- **Two generations per service** — `current` + `previous` only; rollback
  swaps the pointers, no rescanning.
- **Aggregation** — quality_summary, by_version, structOk, completeness are
  computed here from raw per-document data (not in the scanner, not in shared).
- **Phase 3 decision surface** — the org-wide quality picture is read from the
  panel DB; the Jinja-vs-LLM decision is made here, not from a raw JSON dump.
- **Drift** — stores repo HEAD per service; `docs_changed = commit_hash != head_commit`.

Read endpoints never call GitHub; they read stored state. Detailed schema and
the 2-generations model are covered in the panel design issues.

### Gating check

A small workflow-level script reads `report.json` and decides whether the
service is generatable at all. If not, the workflow fails early with a
clear message rather than producing a noisy PR.

Concrete thresholds are tuned empirically. Starting heuristic:

- Service must have at least one endpoint with `overall_status` ≠ `failed`.
- If more than 80% of endpoints are `failed`, gating fails. Reviewer is
  expected to either fix upstream docs or extend the parser before retrying.

These thresholds are data-driven; we revisit them after running the scanner
across the full org.

### Jinja2 generator

- **Owns structure.** File layout, imports, class hierarchy, method
  signatures, boilerplate — all driven by Jinja2 templates against the IR.
- **Output is always syntactically valid Python**, even when the IR has gaps.
  Unknown fragments become FIXME placeholders with safe default values:

  ```python
  timestamp: Any = None  # FIXME_UNKNOWN_TYPE: see RST "Response Parameters"
  ```

- **Determinism is mandatory.** Sorted keys everywhere ordering is not
  semantically meaningful (imports, model fields, methods). `ruff format`
  runs after generation for canonical formatting. No timestamps or build
  metadata in generated code. Without this, maintenance runs (v3) produce
  noisy PRs that don't correspond to real doc changes.
- Reference output structure is the VPC v1 implementation in `python-t-cloud`.

#### Placeholder convention

- Format: `# FIXME_<KIND>: <context>` plus a safe default value.
- `KIND` maps 1:1 to `IssueCode` from the scanner — e.g.
  `FIXME_UNKNOWN_TYPE_FORMAT`, `FIXME_EXAMPLE_INVALID_JSON`,
  `FIXME_NESTED_TABLE_NOT_FOUND`.
- Context string points to the RST source so a reviewer (or the LLM refiner)
  can find the original.
- All placeholders are greppable by `FIXME_` prefix.

### Automatic checks (between Jinja and LLM)

Before invoking the LLM, the workflow runs a series of automatic checks on
the Jinja output:

- **Syntax check** — every generated file is parsed; failure means template bug.
- **Import check** — `python -c "import <module>"` per file.
- **Ruff and mypy** — generated code must pass linting and type-checking.
- **FIXME inventory** — count placeholders by kind. If counts exceed
  per-service baseline (e.g. >10× the VPC v1 reference), workflow fails
  with "templates likely broken, refusing to invoke LLM."

Rationale: these checks catch broken templates before they consume LLM time
and obscure the real problem. They are automatic, fast, and replace what
would otherwise be a manual gate between Jinja and LLM.

### LLM refinement (Ollama)

- **Role:** fill in FIXME placeholders where possible. Never generates structure.
- **Failure mode is graceful:** if Ollama is unavailable, returns invalid
  output, or produces broken Python, the placeholder is left as-is and the
  workflow continues. The PR opens with a single (Jinja-only) commit.
- **Input to each LLM call:** the placeholder + originating RST snippet +
  surrounding code context. Small, focused prompts.
- **Output validation:** each refined fragment is checked for syntactic
  validity in isolation before substitution. Invalid → original FIXME kept.

#### Deployment

**Open question, blocked on Sebastian.** Three candidates:

- **Embedded in CI runner** — Ollama installed and started in the workflow,
  model pulled (or cache-restored), serves localhost. Reproducible, no
  shared state. Cold-start cost on first run per cache window.
- **Self-hosted runner with Ollama preinstalled** — fastest, but requires
  T-Systems to allocate and maintain the machine.
- **Shared Ollama instance in T-Systems infrastructure**, with GitHub-managed
  runners calling over the network — separates persistent LLM hosting from
  ephemeral workflow execution.

The choice affects both runner type and cache strategy. To be decided after
Sebastian's input on what's available.

#### Model selection

- Starting candidate: `qwen2.5-coder:7b` (code-specialized, fits common
  runner RAM).
- Final model TBD after empirical evaluation on real T-cloud documentation.

#### LLM cache

Not part of MVP. Becomes necessary in v3 (maintenance pipeline) where
output stability matters more than speed: without caching, the same prompt
can yield slightly different responses across runs, producing PR diffs that
have nothing to do with actual doc changes.

Cache key: `(model, prompt_hash)`. Storage: T-cloud OBS (see [Service registry
and persistent state](#service-registry-and-persistent-state)). Invalidation
on prompt template version bump or RST source change.

## Git workflow

Each generation produces a branch with **two commits** for traceability:

1. `gen/<service>: baseline via Jinja2` — deterministic template output
   with FIXME placeholders.
2. `gen/<service>: refine via Ollama` — LLM-resolved placeholders. Commit
   body includes model, seed, and resolution stats.

### Rationale for the two-commit split

- `git blame` distinguishes deterministic from LLM-generated lines instantly.
- Reviewer can `git revert <ollama-commit>` to fall back to Jinja-only
  baseline without re-running the workflow.
- `git bisect` localizes regressions to the right stage.
- Diff view on the PR separates structure from content.
- If the Ollama step fails or is skipped, the PR opens with a single
  commit — graceful degradation, no special case to handle.

## PR creation

PRs are opened by a dedicated bot account (`t-sdk-bot` — name TBD), not
from individual contributors' tokens. The bot has write access to
`python-t-cloud` for pushing branches and opening PRs; it does not have
merge rights.

**Why a bot account, not a personal PAT:**

- Generated PRs are clearly attributed as machine-generated.
- Token rotation and revocation are decoupled from individual team members.
- No personal token leakage risk.

The bot account is created as a setup task before MVP launch.

Per Anton: generation checks out `python-t-cloud` into `/tmp` for a stable
target structure, commits and pushes the generated code, and opens one PR per
docs repo. The bot account performs the push and PR creation.

### Branch protection

`python-t-cloud` `main` branch is protected:

- Direct pushes disallowed.
- PR merge requires at least one human review.
- All required CI checks must pass.

This applies uniformly to bot-generated PRs and hand-written PRs.

## CI on auto-generated PRs

Standard CI suite plus:

- **SonarCloud quality gate** (`sonarsource/sonarcloud-github-action`).
  - Free for public repositories.
  - Scope: new code only — existing codebase exempt.
  - Rationale: deterministic Jinja2 output can be verified against the VPC v1
    reference, but LLM-generated content is not verifiable a priori.
    SonarCloud provides external structural validation (smells, security
    hotspots, complexity, duplications, bug patterns).
  - Failure handling: gate fail → PR marked not-mergeable. Reviewer
    decides between re-running with updated template/prompt or waiving a
    specific rule.

## Service registry and persistent state

Service registry maps each generated service to its docs source and tracks
generation state. **Storage: T-cloud OBS** (S3-compatible Object Storage Service).

```yaml
services:
  - name: vpc
    docs_repo: opentelekomcloud-docs/virtual-private-cloud
    sdk_path: src/sdk/services/vpc
    last_generated_sha: abc123...
    last_generated_at: 2026-05-12T08:00:00Z
```

### Why OBS, not Git

- Git-as-state introduces race conditions if two workflow runs update the
  registry concurrently.
- Each registry update would be a noisy commit in `gen-sdk-tooling`.
- OBS supports atomic conditional writes; concurrent updates are serializable.
- T-cloud OBS uses the same AK/SK authentication the SDK already handles —
  no new auth surface.
- The same backend can host the LLM cache (v3), keeping persistent state in
  one place.

## Logs and artifacts

Each workflow run preserves the following as artifacts:

- `report.json` — scanner output (raw per-document results, no aggregates), for post-mortem analysis
- `generated/` — Jinja-only output (commit 1 state)
- `refined/` — final output after LLM (commit 2 state, if applicable)

GitHub Actions retains these for the default 90-day window. No additional
log infrastructure is required.

## Failure handling

| Stage | Failure | Behavior |
|-------|---------|----------|
| Scanner | Docs repo unreachable, parser exception | Fail workflow; Element notification with error details |
| Gating | Too many `failed` endpoints | Fail workflow; reviewer expected to extend parser or fix docs |
| Generator (Jinja) | Template bug, exception | Fail workflow; Element notification; this is a tooling bug requiring fix |
| Automatic checks | Syntax/lint/FIXME-count anomaly | Fail workflow; do not call LLM; investigate templates |
| LLM | Ollama unavailable, invalid output | Continue with FIXMEs unresolved; warning notification; PR opens with single commit |
| SonarCloud gate | Quality issues | PR opens but marked not-mergeable; reviewer decides |
| Push / PR creation | Git or GitHub API error | Fail workflow; retry on next manual trigger |

Principle: **template/parser failures fail loudly because they're our bugs.
LLM failures degrade gracefully because LLM is best-effort enhancement,
not foundation.**

## Quality report (one-off)

The quality report informs the Phase 3 generator decision (Jinja2 sufficient
vs. LLM-assisted). It is produced on the **panel side** by aggregating the
per-service raw scan results stored in the panel DB — not by the scanner
emitting an org-wide `OrgScanResult`. It is rendered in the panel UI (and
exportable as JSON/markdown) once the full org has been scanned
service-by-service.

## Open: generation strategy (Phase 3)

Two of Anton's review comments on the pipeline are recorded here as open
decisions, to be resolved on data from the full-org scan (see Quality report):

- **LLM-primary vs. Jinja-first.** Anton proposes using an LLM for generation
  rather than building the generator from complex Jinja templates. This is
  deferred, not adopted. Decision criteria: regeneration diff-quality on a
  minor RST change, graceful degradation (Jinja baseline opens a PR even if
  Ollama is down), and SonarCloud-verifiability (deterministic output is
  checkable against the VPC v1 reference; LLM output is not a priori).
- **Merge refine into generate (drop step 7).** Anton suggests refining within
  the generate step instead of a separate `gen-sdk-refine` pass. Trade-off:
  this removes the two-commit split (see Git workflow), i.e. the Jinja-baseline
  commit that opens a PR even when the LLM is unavailable. Resolve together
  with the strategy decision above.

## Rollout phases

The full pipeline (initial + maintenance + LLM refinement + caching) is
built incrementally. Each phase delivers a working pipeline; subsequent
phases add capabilities.

### MVP: initial generation, Jinja-only

- Scanner + generator (no LLM)
- `workflow_dispatch` workflow for one-shot generation per service
- Bot account creates PR in `python-t-cloud`
- Automatic checks between Jinja and (absent) LLM step
- SonarCloud quality gate on PR
- Element notification

Goal: prove the pipeline end-to-end on a known service (VPC v1). Validates
infrastructure, permissions, and the bot account setup before adding LLM
complexity.

### v2: LLM refinement

- Add `gen-sdk-refine` step using Ollama
- Two-commit output (Jinja baseline + LLM refinement)
- Notification reports FIXMEs resolved vs. remaining

Goal: handle the ambiguous fragments Jinja can't resolve. Validates Ollama
deployment, model choice, and LLM output stability.

### v3: Maintenance pipeline

- Scheduled workflow detects changes in docs repos
- **Incremental regeneration**: regenerate only files corresponding to
  changed RST sources, leave the rest untouched
- LLM cache in OBS for output stability across runs
- Rich PR descriptions including changed RST list and resolved FIXMEs
- Service registry in OBS tracks `last_generated_sha` per service

Goal: ongoing docs-to-SDK synchronization with minimal noise. This is the
most architecturally demanding phase because of the mapping requirement
(RST file → Python file) and the determinism requirements that make
incremental diffs meaningful.

## Open questions and dependencies

Pre-MVP, requires input from others:

- **Ollama deployment** (Sebastian) — what runner/infrastructure options are
  available. Blocks runner choice.
- **Runner type** (Anton, after Sebastian's answer) — GitHub-managed,
  self-hosted with GPU, or hybrid with shared Ollama.
- **T account for tooling** (Anton).
- **Bot account setup** — needs creating, naming, scoping its PAT permissions.

Lower priority, can be decided as work progresses:

- Specific FIXME-count thresholds for "templates broken" check
- SonarCloud quality gate thresholds
- LLM model selection (decided empirically after first runs)
- Reviewer assignment policy for auto-generated PRs (specific maintainers,
  CODEOWNERS, rotation)