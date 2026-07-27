# Style Guide

Conventions that `ruff`, `lint-imports` and the test suite cannot enforce for
us. Anything they *can* enforce is deliberately absent from this document — if
you find yourself wanting to add a rule here, first check whether it can be a
lint rule, a contract or a test instead. Those never go stale.

Formatting, import order and modernisation are handled by `ruff`
(`E`, `F`, `I`, `UP`; line length 88; target `py310`). Do not argue with it.

## Layers

```
shared  ->  (nothing internal)
scanner ->  shared
panel   ->  shared, scanner
```

`shared` holds the intermediate representation and the scan contracts. It is a
leaf and must stay one: if something in `shared` needs to know about GitHub,
Postgres or FastAPI, it is in the wrong module.

Analytics - the pure computation over scan results, with no I/O, no clock and no
network - belongs to `panel/core/analytics/`. Purity is what makes it testable
without fixtures, so keep it that way wherever it lives.

**`tools.domain` is on its way out.** It currently holds the organization-level
report, which is being removed along with `ScannerService.scan_organization()`
and `OrgScanResult`; the reusable analytics move into `panel/core/analytics/`.
See **#34**. Add nothing new to `tools.domain`, and do not build on
`OrgScanResult`. Note that the legacy `--org` scan path still imports it from
`scanner/main.py` and `scanner/service.py`, so the removal has to deal with that
first.

`lint-imports` enforces the contracts in `pyproject.toml`. Anything it does not
cover is convention - if a layer rule is worth keeping, add the contract rather
than a paragraph here.

What no contract can enforce is intent, and two failures pass the linter while
being real problems: a domain rule implemented inside `scanner` (a decision
about what "partial" means, hidden in a parser), and an infrastructure heuristic
implemented inside the analytics (a GitHub-shaped assumption in a counting
function). Watch for both.

## Models

- **Pydantic `BaseModel`** for anything serialized or validated — IR entities,
  scan results, API schemas. Always `model_config = ConfigDict(extra="forbid")`:
  an unexpected key is a contract change and must fail loudly.
- **Frozen dataclass** for internal value objects that never cross a
  serialization boundary, e.g. `RepositoryInterruption`.
- **`Protocol`** for ports (`DocProvider`, `RstParser`). Ports describe what the
  scanner needs, not what GitHub offers; keep provider-specific vocabulary out of
  them.

Invariants belong in validators, next to the data, not in the callers:

```python
@model_validator(mode="after")
def validate_field_metrics(self) -> Self:
    accounted = self.fields_recognized + self.fields_unknown_type + self.fields_failed
    if accounted != self.fields_total:
        raise ValueError(...)
```

A validator is worth more than a comment and more than a paragraph here: it
fails at the moment the invariant breaks, in every code path at once.

## One source of truth

Every status, code and schema version has exactly one definition, and
`docs/GLOSSARY.md` says where. Import it; do not retype it.

The characteristic failure of code written across many sessions is a *local*
source of truth: an enum in `shared`, and three modules later the same strings
as literals, or a second enum with a different suffix. Two names for one fact
drift, and the drift is silent because both halves look correct in isolation.

Before adding a name, grep for it. After adding one, record it in the glossary.

## Errors

The hierarchy is `GenSdkError` and its subclasses in
`src/tools/shared/exceptions.py`:

- `ProviderError` — a normalized external failure, carrying a
  `ProviderErrorKind`. Providers translate their own exceptions into this so
  upper layers never import `requests`.
- `ParseFailure` — a gating parse failure. Carries an `Issue`; the scanner layer
  catches it and converts it into `DocumentScanResult.failure_reason`.
- `ConfigurationError` — invalid or missing configuration.

No bare `except:`. No `except Exception` without re-raising or recording an
`Issue`. An exception that is swallowed to keep a loop going has to leave
evidence that it happened.

## Data may not disappear quietly

This is the rule this codebase exists to uphold, so it gets the most space.

The output of the scanner is counted, aggregated and used to decide which
services are ready. Rank defects not by whether they crash, but by how likely
anyone is to notice them:

- **A crash** is the cheapest. It is seen immediately and fixed the same day.
- **A wrong value** costs more, but it usually surfaces when someone reconciles
  the numbers - a count does not add up, or a figure looks absurd.
- **Missing data** is the most expensive, because nothing surfaces it. The
  result stays plausible, so nobody goes to check it.

Concrete patterns to avoid, all of which have appeared in generated code before:

**Warning-only failure.** `logger.warning(...)` and then returning partial data
with an OK status. The log line is invisible to every consumer downstream. If
the result is incomplete, say so in the result: `incomplete_reason`,
`interruption`, a non-OK `SectionStatus`, or an `Issue`.

**Denominator escape.** An item that should count as failed gets moved into an
excluded or not-applicable bucket instead. Quality metrics improve because
broken items left the denominator rather than failing inside it. If you add a
new exclusion path, ask what it removes from which count, and say it in the PR.

**Zero by construction.** An `IssueCode` or status that can never be produced,
because an upstream filter removes its inputs. It will report `0` forever and
readers will conclude the problem never occurs. Every declared code should
either be reachable on the production path or be documented as reserved for a
named future feature.

**A guard that never runs.** The mirror image of the previous one: there the
*status* is unreachable, here the *branch* is. A condition that cannot be true, an
`except` clause for an exception that is caught earlier, a validation function
nobody calls. The code reads as protection, so the next person assumes the case
is handled - and it is not. Unreachable code is not merely dead weight; it is a
false statement about what the program checks.

**Guess without a trace.** A fallback assignment - unlabeled example becomes
`request`, unknown type becomes `UNKNOWN` - with nothing recorded. Downstream
cannot then measure how much of the data was guessed. Emit the `Issue`
(`EXAMPLE_UNLABELED`, `UNKNOWN_TYPE_FORMAT`) even when the fallback is
reasonable.

**Trusting the server.** "The page was shorter than the limit, so we are done" -
servers cap limits, proxies strip query parameters. GitHub's recursive tree
endpoint returns HTTP 200 with a partial list and `truncated: true`; that is why
`FileListing` carries a flag and why `RepositoryScanResult` has
`incomplete_reason`. Treat every listing as potentially truncated until the
provider says otherwise.

**Extension paths skipping validation.** When an "already exists, just add to
it" branch bypasses the recomputation the creation branch performs, the second
item silently gets no status and no issues.

## Metrics must reconcile

Counts that describe the same set must add up, and the check belongs in code:
`fields_recognized + fields_unknown_type + fields_failed == fields_total` is
already a validator. When you add a count, add its reconciliation with it.
Derived values are computed once, in the analytics module, and never
duplicated into a second loop somewhere else.

## Logging

Module-level `logger = logging.getLogger(__name__)`. Never `print` outside CLI
output. Levels: `DEBUG` for tracing, `INFO` for progress, `WARNING` for a
recoverable anomaly *that is also recorded in the result*, `ERROR` for a failure
being reported upward. A log line is for the operator; it is never the record of
what happened.

## Typing and small things

- `from __future__ import annotations` in modules with forward references.
- `X | None`, not `Optional[X]`.
- Keyword-only arguments for anything with more than two parameters of the same
  type — `def f(*, job_id: int, service_repo: str)` cannot be called in the
  wrong order.
- Prefer explicit `isinstance` narrowing over `hasattr` probing when working
  with the polymorphic IR entities (`Document` vs `Endpoint`, `Repository` vs
  `Service`).

## Docstrings and comments

Module docstrings on every module that is not trivially named. Docstrings on
public functions, ports and models. Write *why*, not *what* - the signature
already says what.

A comment earns its place when it carries something the next person needs in
order to change this code safely: a constraint, a non-obvious mechanism, a
consequence that is not visible from the line itself.

```python
# RepositoryScanResult depends on IR, while IR entities embed the eagerly
# exported document/section scan results. Defer only repository-level
# exports to keep the public facade without creating an import cycle.
```

That one is worth keeping: without it, the next person inlines the import and
breaks the package.

What does not belong in a comment is the deliberation behind a decision - "we
considered X, went with Y", "written this way because that is how it is done in
Go". That is history, not a constraint; it goes stale, and it is invisible to
anyone who has not opened this exact file. It belongs in the pull request or the
issue.

And when a constraint can be pinned by a test, pin it by a test. A test states
the same thing, cannot drift away from the code, and fails when someone breaks
it.

## Seams and deferred work

A seam names its issue, or it is dead code:

```python
raise NotImplementedError("F2 ingest — see #23")
# TODO(#23): transition the job to done/failed here
```

Bare `TODO` and `FIXME` without a number are not accepted: nothing can tell them
apart from an abandoned experiment, and eventually something will delete them.

## Tests

- `pytest`, tests in `tests/`, one file per subject
  (`test_scanner.py`, `test_panel_db.py`). Test names say the scenario and the
  expectation.
- Shared RST fixtures live in `tests/fixtures/` and are loaded through the
  helpers in `tests/conftest.py`. Add a real document rather than inventing RST
  by hand — the point of these fixtures is that upstream really looks like this.
- Prefer `monkeypatch` over threading factory or injection parameters through
  production signatures. Production code stays plain; the test does the
  substitution.
- Database tests need PostgreSQL. Do not add SQLite fallbacks: the schema relies
  on partial unique indexes and CHECK constraints that SQLite does not enforce,
  so a green SQLite run would be a false negative.

### Tests versus code

When a test fails after a change, decide which side encodes the specification
*before* editing either.

A mock that behaves badly is usually not an unrealistic mock — it is a model of
an adversarial server. A fake provider that returns the same non-empty page for
any request encodes a real termination requirement, and the correct response is
to fix the loop, not to make the mock nicer.

Tests may be updated in their interaction details — call counts, argument order —
but their data assertions may only change if you can show the test itself
encoded the bug. If a change touches a loop's exit condition, re-read every test
whose fake answers unconditionally, including the one named `test_single_page`.
