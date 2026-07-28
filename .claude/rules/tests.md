---
description: Test conventions and how test-versus-code conflicts are settled
paths:
  - "tests/**"
  - "frontend/src/**/*.test.ts"
  - "frontend/src/**/*.test.tsx"
---

The conventions themselves live in `STYLEGUIDE.md`, section **Tests** - flat
functions under section banners, hand-written fakes over `unittest.mock`,
docstrings only on tests that protect a non-obvious invariant, fixtures through
`load_fixture()`. Read that section before writing tests. What follows is what
tends to be forgotten in the moment.

- **PostgreSQL is required** for panel tests: `TEST_DATABASE_URL`, or Docker so
  testcontainers can start `postgres:16-alpine`. Both paths pin
  `sslmode=disable` in `tests/test_panel_db.py`, because a test container
  speaks no TLS and libpq would otherwise honour a `PGSSLMODE` set for some
  other database - a failure that hits only the developers who have that
  variable. A connection failure is still an environment problem: report it as
  that, not as a defect in the code.
- **New vocabulary needs a reachability test.** A new `IssueCode` or status
  needs a test that actually produces it, or you cannot tell "never happens"
  from "cannot happen".
- **A failing test is an argument, not an obstacle.** Decide which side encodes
  the specification before editing either. A fake that returns the same
  non-empty page for every request is a model of an adversarial server and
  encodes a real termination requirement: fix the loop, not the fake.
  Interaction details - call counts, argument order - may be updated. Data
  assertions may only change if you can show the test itself encoded the bug.
- **Coverage:** total at least 75%, new and changed lines at least 80%. Deleting
  a test to make a gate pass is not an option available to you.
