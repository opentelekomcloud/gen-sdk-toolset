---
name: pr
description: Draft the pull request description for the current branch in this project's established format.
argument-hint: "[extra context]"
disable-model-invocation: true
---

Draft a pull request description for the current branch. Extra context:
`$ARGUMENTS`

Gather first:

```bash
git log --oneline origin/main...HEAD
git diff --stat origin/main...HEAD
```

Write it in the format this repository already uses:

**A lead paragraph per theme.** Group the changes by what they accomplish, not
by directory. Open each group with a couple of sentences saying what the group
does and why, then list the files it touches.

**One entry per file**, as a markdown link to the path, followed by a short
paragraph in prose - what this file's responsibility is now, and what changed
about it. Mark new and moved files with `**[NEW]**` and `**[MOVED]**`. Explain
the responsibility, not the diff: the reviewer can read the diff, what they
cannot read is the intent.

**Deliberately deferred work**, with issue numbers, and where in the code the
seam sits. Reviewers need this so they ask for the accounting rather than for
the work.

**Checks run**, matching the Definition of Done in `AGENTS.md`. Say which ones
you actually ran. If something is red or unverified, say that instead of leaving
it out.

Three constraints on what you write, in order of how easily they are broken:

- **Do not claim a check passed without having run it.** If you did not run one,
  write "not run" and stop there. Do not supply a reason why it was unnecessary
  - a reason you invented reads exactly like a reason you verified.
- **Do not describe a file you have not read in this session**, and do not
  describe a change you have not seen in the diff. "Adds X to `.gitignore`" is a
  claim about a diff: check that X is not already there.
- **Do not narrate project history.** Sentences like "every previous attempt
  drifted" or "this has been a problem for the team" are invented unless
  somebody wrote them down somewhere you can cite. Describe the change, not a
  backstory for it.

If you are unsure whether something is true, leave it out. A short description
of what actually changed is worth more than a complete-looking one with two
confident errors in it.
