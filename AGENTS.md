# AGENTS.md

Automated Python SDK generation from Open Telekom Cloud (OTC) API
documentation. Two components exist today: a **scanner** that walks
`opentelekomcloud-docs` repositories and turns RST API-reference pages into a
structured intermediate representation, and a **panel** (FastAPI + React) that
stores and displays scan results. The SDK code generator is not built yet — do
not write code that assumes it exists.

This file is the entry point for coding agents. Rules that apply to one area
only live in `.claude/rules/` and load automatically when you touch that area.

## Before you write anything

Find the module closest to what you are about to build, open it, and mirror its
shape - imports, docstring style, error handling, test layout - before writing
anything new.

Never guess a convention when an existing file already answers the question.
The documents here give you the pattern; the codebase gives you the proof. Where
the two disagree, read the code and say so, rather than silently following
either one.

## Setup

```bash
uv sync --extra dev --extra panel      # Python deps (3.10+)
cp .env.example .env                   # then set GITHUB_TOKEN=ghp_...
cd frontend && npm ci                  # frontend deps
```

`GITHUB_TOKEN` is deliberately kept out of the TOML config: it lives in `.env`
or the environment only.

## Commands

| Task | Command |
|---|---|
| Lint | `ruff check .` |
| Format | `ruff format .` (check only: `ruff format --check .`) |
| Architecture boundaries | `lint-imports` |
| Tests + coverage | `uv run pytest --cov --cov-report=term-missing --cov-report=xml` |
| Diff coverage | `uv run diff-cover coverage.xml --config-file pyproject.toml --compare-branch=origin/main` |
| Scan one repository | `uv run gen-sdk-scan --repo opentelekomcloud-docs/anti-ddos --output -` |
| Regenerate API schema | `uv run panel openapi > src/tools/panel/openapi.json` |
| Regenerate frontend types | `cd frontend && npm run gen:types` |
| Frontend | `cd frontend && npm run lint && npm run build && npm run test:coverage` |

Tests touching the panel database need PostgreSQL. Either export
`TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres`
or let testcontainers start `postgres:16-alpine` (Docker must be running).
A database connection failure is an environment problem, not a code finding —
say so instead of reporting it as a defect.

## Layout

```
src/tools/
  shared/     IR models + scan contracts. Leaf: imports nothing internal.
  domain/     Legacy org-level report, being removed - see issue #34. Add nothing
              here; the reusable analytics move to panel/core/analytics/.
  scanner/    GitHub provider, RST parsers, ScannerService.
  panel/      FastAPI API, SQLAlchemy models, Alembic migrations, jobs.
frontend/     React + TypeScript (Vite, TanStack Query).
tests/        pytest suite; RST fixtures in tests/fixtures/.
docs/         Architecture, glossary, recipes.
```

Dependency direction is enforced by `lint-imports` (contracts live in
`pyproject.toml`). Note what it cannot see: it checks imports, not meaning. An
infrastructure heuristic that has drifted into the analytics, or a rule about
what "partial" means that has leaked into a parser, passes the linter. Those are
yours to catch.

## Vocabulary

`docs/GLOSSARY.md` is the canonical list of domain names — entities, statuses,
issue codes, schema versions — and where each one is defined. Before adding a
new enum member, status string or constant, check whether it already exists.
Never re-declare a value as a literal next to code that could import it: that is
how two sources of truth for one fact get created, and it is the single most
common defect in multi-session generated code.

## The rule that matters most in this repository

This project's output is a set of numbers that decide which OTC services are
ready for SDK generation. A crash is cheap. A silent loss is expensive, because
the number still looks plausible: a dropped document, a failure reclassified
into an excluded bucket, a truncated listing returned with a clean status.

So: **data may never disappear quietly.** Anything dropped, guessed, truncated
or defaulted must leave a machine-readable trace — an `Issue`, an
`incomplete_reason`, an `interruption`, or a non-OK status. A `logger.warning`
followed by a clean return is not a trace.

## Definition of Done

A change is done when all of these pass locally — not when the plan looks
complete:

- [ ] `ruff format .`, then `ruff check .` (that order - the formatter moves
      lines the linter then judges)
- [ ] `lint-imports`
- [ ] `uv run pytest` green, with no skips you introduced
- [ ] New and changed lines covered at least 80% (`diff-cover`); total stays at least 75%
- [ ] Frontend touched? `npm run lint && npm run build && npm run test:coverage`
- [ ] Panel routes or schemas touched? `src/tools/panel/openapi.json` and
      `frontend/src/shared/api/schema.gen.ts` regenerated and committed
- [ ] New vocabulary recorded in `docs/GLOSSARY.md`

If a check fails and you cannot fix it, say which one and why. Do not report a
task as finished with a known-red check.

## Boundaries

**Always**

- Read a file before editing it. Never describe or edit code from memory of an
  earlier skim.
- Stay inside the scope you were given. Note anything else you notice instead of
  fixing it silently in the same change.
- Extend an existing module rather than creating a parallel one beside it.

**Ask first**

- Adding a runtime dependency to `pyproject.toml`.
- Changing the database schema (this needs an Alembic migration).
- Changing a serialized contract: `REPORT_SCHEMA_VERSION`,
  `DOCUMENT_SCHEMA_VERSION`, panel routes, `openapi.json`.
- Deleting code that appears to have no caller — run the `gc` agent first.
- Relaxing a validator, CHECK constraint or unique index.

**Never**

- Edit an already-applied migration in
  `src/tools/panel/core/db/migrations/versions/`. Write a new one.
- Lower the coverage gates in `pyproject.toml`, or scatter `# noqa` /
  `# type: ignore` to make a check pass. Fix the cause, or report it unfixed.
- Commit `.env`, tokens or any real credential.
- Hand-edit generated artifacts (`src/tools/panel/openapi.json`,
  `frontend/src/shared/api/schema.gen.ts`). Regenerate them.
- Weaken a test's data assertions to make it pass — see STYLEGUIDE.md,
  "Tests versus code".
- Delete scaffolding that names an open issue.

## Scaffolding

Work is deliberately left unfinished sometimes. A seam is legitimate only if it
names its issue, so that anyone — including an agent that has never seen the
plan — can check whether it is still wanted:

```python
def ingest_service_result(...) -> None:
    raise NotImplementedError("F2 ingest — see issue #23")
```

`# TODO(#23): ...` in a comment works the same way. A seam with no issue number
is indistinguishable from forgotten dead code and will eventually be treated as
such. Plans live outside this repository; the issue number is the only link
that survives.

## Where the rules live

| File | Contents |
|---|---|
| `CONTRIBUTING.md` | Branches, commit format, pull request process |
| `STYLEGUIDE.md` | Python conventions not enforced by tooling |
| `docs/GLOSSARY.md` | Canonical domain vocabulary |
| `docs/FAQ.md` | How to do the common tasks, with working examples |
| `docs/architecture.md` | Intended system shape |
| `.claude/rules/*.md` | Area rules, loaded automatically by path |

Keep this file short. If a rule can be enforced by ruff, import-linter or a
test, put it there instead of writing it here.
