---
name: review
description: Review generated code for duplicated vocabulary, silently dropped data and unreachable statuses. Defaults to the current branch against main.
argument-hint: "[--full | --pr <ref>]"
disable-model-invocation: true
context: fork
agent: ai-code-review
---

Run a review with the method in `.claude/agents/ai-code-review.md`.

Arguments: `$ARGUMENTS`

Pick the mode from them:

- **empty** - branch mode. Scope `origin/main...HEAD`. This is the default and
  the one to run before opening a pull request.
- **`--pr <ref>`** - review that branch or pull request as someone else's work:
  read-only, deliverable is a review comment, and include the questions to the
  author.
- **`--full`** - whole-repository audit. Only when explicitly asked; it is slow.

Before starting:

1. `git diff --name-only origin/main...HEAD` (or against the given ref) to see
   the scope, and apply the depth-escalation table - parser, analytics and
   report changes require the data cross-check, `shared` changes require the
   full vocabulary registry.
2. `git log --oneline origin/main...HEAD` to see what the author was doing, and
   note any `:construction:` commits - those are declared seams, not defects.
3. Read `docs/GLOSSARY.md` before the vocabulary check. It is the canon you are
   comparing against.

Never change git state to do any of this - no checkout, no stash, no branch
switching. Read other refs with `gh pr diff` and `git show <ref>:<path>`. The
working tree may hold uncommitted work that is not yours.

Do not write a review file into the repository. Return the review; the fix and
the guard are what survive.
