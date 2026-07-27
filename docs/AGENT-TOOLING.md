# Agent tooling

This repository ships a small amount of shared configuration for AI coding
agents: three commands you type, three specialised agents you delegate to, and
some rules and hooks that apply themselves. It lives in `.claude/` and is
committed, so everyone on the project gets the same behaviour.

This page is for people. The agents read `AGENTS.md`.

## Prerequisites

**Install the GitHub CLI.** `/plan`, `gc` and `ai-code-review` read issue state
through it; `git` cannot, because issues are not part of git.

```bash
winget install GitHub.cli     # Windows
brew install gh               # macOS
# other systems: https://cli.github.com
gh auth login
```

**Start the agent in the repository root.** Everything here activates only when
that is the working directory:

```bash
cd path/to/gen-sdk-toolset
claude
```

A session started in a subdirectory will not load any of it. The configuration
is read once at startup, so if you pull a change to `.claude/` while a session
is open, restart it.

To check that it loaded, type `/` and look for `review`, `plan` and `pr` in the
list. If they are missing, the working directory is wrong or the session
predates the files.

## The three commands

None of them is invoked automatically. Nothing happens until you type it.

### `/plan [issue number or description]`

Writes an implementation plan in the format this project already uses: what
already exists, what is in scope, what is deferred and to which issue, the files
involved, component design with the reasoning, data flow, test plan, and an
ordered checklist. It reads the issue and the code it is about to change before
planning.

Run it before writing code. Its value is not the document — it is that two
people planning in the same shape produce code in the same shape.

It ends by re-reading its own plan for over-engineering, which is where most of
its usefulness turns up: injection seams a `monkeypatch` would cover,
abstractions with one implementation, parameters that will always be passed the
same value.

### `/review [--full | --pr <ref>]`

Reviews code for the defects that AI generation characteristically produces —
duplicated vocabulary, silently dropped data, statuses that can never fire. It
runs in a separate agent with its own context, so it does not fill your session
with the files it read.

- `/review` — the current branch against `main`. Run it before opening a PR.
- `/review --pr <ref>` — someone else's branch. Read-only, produces a review
  comment, and adds two or three questions to the author.
- `/review --full` — the whole repository. Slow; for release time or after a
  large generation push.

Depth escalates automatically with what the diff touches: changes to parsers or
analytics trigger a cross-check against real scanner output, changes to `shared`
trigger a full vocabulary audit.

Two things it deliberately does not do. It does not edit code — a reviewer who
also fixes stops being able to tell a real finding from one invented to have
something to fix. And it does not write a review file into the repository: once
a finding is closed, its description only describes code that no longer exists.
What survives a review is the fix and the guard.

### `/pr`

Drafts the pull request description for the current branch from its commits and
diff: a lead paragraph per theme, one entry per file explaining what that file
is now responsible for, deferred work with issue numbers, and the checks that
were actually run.

## The three agents

Invoke these with `@name`, or let the agent delegate to them when a task matches
their description. `/review` already forks into `ai-code-review`, so that one
needs no direct call.

| Agent | The question it answers |
|---|---|
| `ai-code-review` | Does this code silently lose or duplicate something? |
| `gc` | Can anything still reach this code? |
| `simplify` | This code is needed — is there a smaller way to write it? |

`gc` and `simplify` are deliberately separate, because the two questions carry
very different risk. Asking whether something is *needed* requires proving that
nothing reaches it, and getting it wrong destroys work. Asking whether needed
code could be *shorter* is nearly free.

**`gc`** works like a garbage collector, and the order is the point: it marks
everything reachable from explicit roots first — entry points, routers, the
Alembic environment, every test, external contracts, and any `TODO(#N)` whose
issue is still open — and only then looks at what is left. It never deletes; it
reports candidates with the roots it searched and its confidence. When in doubt,
code lives: keeping something dead costs a little reading, deleting a
deliberate scaffold costs re-deriving design work.

While plans are not stored in the repository, `gc` is restricted to the diff.
Recent unreachable code is probably over-generation; old unreachable code is
where deliberate scaffolding lives, and it is out of scope.

**`simplify`** walks a ladder — reuse what exists, then the standard library,
then the framework already installed, then fewer moving parts, then a shorter
expression — and stops at the first rung that applies. It never touches
validation at a trust boundary, anything that records data loss, error handling
that produces a diagnostic, constraints, or anything with a live consumer.

## What applies itself

**Path-scoped rules.** `.claude/rules/*.md` load when the agent touches the
matching area and stay out of the context otherwise.

| Rule | Loads for |
|---|---|
| `shared.md` | `src/tools/shared/**` |
| `scanner.md` | `src/tools/scanner/**` |
| `panel.md` | `src/tools/panel/**` |
| `frontend.md` | `frontend/**` |
| `tests.md` | `tests/**` and frontend tests |

**Two hooks**, declared in `.claude/settings.json`.

Before every file edit, a guard refuses three things: touching `.env`, editing a
generated artifact (`openapi.json`, `schema.gen.ts`), and editing a migration
revision **that git already tracks**. That last distinction is deliberate — a
freshly autogenerated revision is untracked, so correcting what Alembic missed
still works; once it is committed it may have been applied, and you write a new
one instead.

After every Python file edit, `ruff format` and `ruff check --fix` run on that
one file, so mechanical issues never reach review. This adds roughly a second
per edit. Both hooks stay silent when they cannot do their job rather than
blocking work — which means a missing `ruff` fails quietly.

**Permissions.** `settings.json` also pre-approves the commands used constantly
(`uv run pytest`, `ruff`, `lint-imports`, read-only `git` and `gh`, `npm run`)
and denies `git push --force`, `git reset --hard`, `rm -rf` and reading `.env`.
Treat the deny list as convenience rather than a security boundary: it closes
the obvious door, not every door. The real protection for the token is that
`.env` is gitignored.

**Personal overrides** go in `.claude/settings.local.json`, which is gitignored.
Use it if a hook command does not work on your machine — do not change the
shared file for a local problem.

## A task, start to finish

```
/plan 34              # plan, read it, adjust it
                      # write the code; formatting applies itself
/review               # fix what it finds; add a guard for each fix
/pr                   # paste into GitHub
```

`@gc` and `@simplify` are occasional rather than per-task: run them when a
module feels like it accumulated things, not on every change.

## If something does not work

None of this has been exercised much yet. If a command does not appear, check
the working directory first and restart the session second. If one appears but
behaves oddly, the frontmatter in its `SKILL.md` is the place to look. Report
what broke rather than working around it — these files are meant to be edited.
