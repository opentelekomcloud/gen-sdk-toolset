# Contributing

This is the process for humans. Agents read `AGENTS.md`, which points back here.

## Getting set up

Installation, configuration, and how to run the scanner and the panel are all in
[README.md](README.md). One thing it does not cover: database-backed tests need
PostgreSQL. Either set `TEST_DATABASE_URL`, or run Docker and let testcontainers
start `postgres:16-alpine` for you.

## Branches

One branch per issue, named `<type>/<issue-number>-<short-slug>`:

```
feat/21-background-scan-job
fix/57-truncated-listing-reported-clean
docs/85-agent-guides
```

The type is one of the same set the commits use - `feat`, `fix`, `refactor`,
`test`, `docs`, `chore` - so there is one vocabulary rather than two. The issue
number is not decoration: it is what links the branch to the work it came from,
and `gh pr create` picks it up.

Creating the branch from the issue on GitHub suggests a name without the
prefix - the field is editable in that dialog, so add it there rather than
renaming afterwards.

Branch from `main`; never commit to `main` directly.

## Commits

A conventional-commit subject with a scope is required. A gitmoji prefix in
front of it is optional - use it if you enjoy it, skip it if you do not. Both of
these are fine:

```
:sparkles: feat(panel): add scan launch and job polling endpoints
feat(panel): add scan launch and job polling endpoints
```

Scopes in use: `scanner`, `panel`, `frontend`, `shared`, `test`, `docs`, `ci`.

If you do use gitmoji, these are the ones already in the history:

| Emoji | Type | Use for |
|---|---|---|
| `:sparkles:` | feat | New behaviour |
| `:bug:` | fix | Wrong behaviour |
| `:rotating_light:` | fix | Linter, type-checker or CI complaints |
| `:recycle:` | refactor | Same behaviour, different shape |
| `:white_check_mark:` | test | Tests only |
| `:memo:` | docs | Documentation only |
| `:wrench:` | chore | Config, tooling, dependencies |
| `:construction:` | feat | A seam or scaffold - name its issue in the body |

Keep commits small and single-purpose. During review, append commits rather than
squashing and force-pushing, so the reviewer can see what changed since they
last looked.

## Pull requests

Open the PR against `main` and fill in the template. It asks for the same things
every time on purpose: what changed, why, what was deliberately left out, and
which checks were run.

CI must be green before merge. The pipeline runs, in four parallel jobs:

- **lint** — `ruff check .`, `ruff format --check .`, `lint-imports`
- **tests** — `pytest` with coverage against a real PostgreSQL service, then
  `diff-cover` against the base branch
- **frontend** — ESLint, typecheck + build, Vitest with a coverage gate
- **artifacts** — regenerates `openapi.json` and `schema.gen.ts` and fails on any
  diff, so a contract change cannot merge without them

Coverage gates: the project total must stay at or above **75%**, and new or
changed lines must reach **80%**. Raising the total is welcome; lowering either
gate to make a build pass is not — fix the code or explain the gap in the PR.

## Reviews

Review is run with `/review`; see
[docs/AGENT-TOOLING.md](docs/AGENT-TOOLING.md) for that and the rest of the
agent tooling. Whether a human or an agent runs it, the same two rules apply:

1. A review finding must leave behind a fix, a guard (a test or a lint contract),
   or nothing at all. Review documents are not committed — once the finding is
   closed, its description only describes code that no longer exists.
2. Severity is measured in hours the next person has to spend, not in taste.
   Anything that can distort the numbers the panel reports is blocking, even if
   the code runs and the tests are green.
