# Glossary

The canonical list of domain names and where each one is defined. This file has
a job beyond documentation: it is the reference list used when checking whether
new code invented a second name for an existing fact.

**Rules.** One definition per concept. Import it, never retype it as a literal.
Adding a name to the code means adding it here in the same change. If a name you
need is missing, add it here first and then implement it.

## Entities — the intermediate representation

Defined in `src/tools/shared/ir/`. Serialized shape is versioned by
`DOCUMENT_SCHEMA_VERSION`.

| Name | Where | Meaning |
|---|---|---|
| `Repository` | `ir/repository.py` | A GitHub repository, identified by `repo` (`owner/name`). The base case: a repository we looked at but which has no API reference. |
| `Service` | `ir/service.py` | A `Repository` that is eligible — it has an `api-ref/source` directory. Carries `documents`. |
| `Document` | `ir/document.py` | One file we processed, identified by `path`. Carries a `DocumentScanResult`. A plain `Document` without a failure is a successfully scanned non-endpoint page. |
| `Endpoint` | `ir/endpoint.py` | A `Document` recognized as describing one API operation: `method`, `uri`, `api_version`, and exactly one `Section` per `SectionName`. |
| `Section` | `ir/section.py` | One extracted part of an endpoint document. Carries `parameters`, `examples` and a `SectionScanResult`. |
| `Parameter` | `ir/parameter.py` | One field from a parameter table. Nests through `children`. |
| `Example` | `ir/example.py` | One request or response example. `raw` always; `parsed` only when it is valid JSON. |
| `kind` | all of the above | The polymorphic discriminator: `repository`, `service`, `document`, `endpoint`. It is how subclasses survive a round trip through JSON. |

`SectionName` (`ir/section.py`) — the seven sections every `Endpoint` must have:
`path_params`, `query_params`, `headers`, `body`, `response`, `example_request`,
`example_response`. A section that was not present in the document is still
recorded, with status `missing`.

`HttpMethod`, `ParameterType` (`ir/enums.py`) — HTTP verbs, and the types found
in OTC parameter tables including the composite ones (`Array of strings`) and
the `Unknown` fallback.

## Scan results — what one scanner session produced

Defined in `src/tools/shared/scan/`. These are contracts: the panel and the
frontend read them.

| Name | Where | Meaning |
|---|---|---|
| `RepositoryScanResult` | `scan/repository.py` | The snapshot of one repository scan: the `repository` (or `Service`), `branch`, `commit_hash`, `scanner_version`, `excluded_documents`, plus failure fields. |
| `DocumentScanResult` | `scan/document.py` | Per-document diagnostics. Currently one field: `failure_reason`, an `Issue` that gated the document. |
| `SectionScanResult` | `scan/section.py` | Per-section diagnostics: `status`, `issues`, `unmatched_tables`, and the four field counters. |
| `Issue` / `IssueCode` | `scan/issue.py` | One structured problem: a machine-readable `code`, an optional `location` and `details`. |
| `SectionStatus` | `scan/section.py` | `ok`, `partial`, `failed`, `missing`. |
| `RepositoryInterruption` / `RepositoryInterruptionKind` | `scan/repository.py` | An operational reason the scan stopped: `rate_limit`, `authentication`, `permission_denied`, `repository_failure`. |

Two fields describe two different kinds of "not clean", and they are not
interchangeable:

- **`error`** — the repository-level scan failed (for example, listing files
  failed, a truncated file listing, or a transport failure while fetching
  document content). Mutually exclusive with `interruption`.
- **`interruption`** — the scan stopped for an operational reason outside the
  documents themselves.

`incomplete_reason` (a soft "finished, but on a truncated input" marker) was
removed from `RepositoryScanResult`, the `Generation` DB column, and the
frontend generation badge: every scenario that used to set it (a truncated
file listing) now fails the whole scan via `error` instead, so the field had
no remaining producer anywhere in the scanner.

The field counters on `SectionScanResult` must reconcile:
`fields_recognized + fields_unknown_type + fields_failed == fields_total`.

## Derived analytics

Currently in `src/tools/domain/report/`, **being relocated to
`src/tools/panel/core/analytics/` by issue #34**. Nothing here is stored in the scan
snapshot - it is computed from it, in one place. Add nothing new to
`tools.domain`.

| Name | Where | Meaning |
|---|---|---|
| `OverallStatus` | `report/enums.py` | Document-level roll-up: `ok`, `partial`, `failed`, `unsupported`. `unsupported` specifically means the document style was not recognized. |
| `QualitySummary` | `report/analytics.py` | `by_overall_status`, `by_section_status`, `top_issues`. |
| `doc_overall_status`, `doc_all_issues`, `count_by_version` | `report/analytics.py` | The pure functions the roll-ups are made of. These are the reusable part that moves to the panel. |

`OrgScanResult` and `REPORT_SCHEMA_VERSION` (`report/aggregates.py`) are the
organization-level report contract. They are **scheduled for removal** together
with `ScannerService.scan_organization()` - see issue #34. Do not build on them.

## Panel — the persisted model

Defined in `src/tools/panel/core/db/models.py`. Note the name collision and mind
it: `Service` here is a database row, not the IR entity above.

| Name | Meaning |
|---|---|
| `Service` (table `service`) | A tracked repository, keyed by the unique `repo`. Holds eligibility, discovery state, and pointers to its active and latest `Generation`. |
| `ExcludedService` | A `Service` deliberately excluded, with `reason` and `excluded_by`. |
| `Generation` | One ingested scan: `branch`, `commit_hash`, `scanner_version`, `document_schema_version`, the roll-up counters and `analytics`. |
| `DocumentRecord` (table `document`) | One document inside a `Generation`: the full IR `payload` plus the columns denormalized for querying. |
| `RepositoryScanJob` (table `job`) | One scan run: `kind`, `status`, `initiated_by`, timestamps, `error`, `interruption`. |
| `JobKind`, `JobStatus` | `JobStatus` is `queued`, `running`, `done`, `failed`. |

Two database constraints carry rules that code depends on, so do not weaken them
without reading their consumers first: the `status_timestamps` CHECK constraint
encodes the job lifecycle (`queued` has no `started_at`; `running` has
`started_at` and no `finished_at`), and the partial unique index
`uq_active_scan_job_per_service` allows at most one `queued` or `running` scan
job per service — it is what makes the API's `409` response correct rather than
racy.

## Versions

| Name | Where | Covers |
|---|---|---|
| `__version__` | `src/tools/__init__.py` | The scanner/parser version, read from package metadata and stamped on every result. Lets consumers tell "docs changed" apart from "parser improved". |
| `DOCUMENT_SCHEMA_VERSION` | `shared/ir/__init__.py` | The serialized `Document`/`Endpoint` contract. |
| `REPORT_SCHEMA_VERSION` | `domain/report/aggregates.py` | The organization-level report contract. Being removed with issue #34 - do not build on it. |

## Scanner vocabulary

| Term | Meaning |
|---|---|
| **Style A / Style B** | Two documentation shapes found upstream. Style A is the Function / URI / Request / Response layout the parser supports. Style classification happens in the scanner *before* the parser runs, so the parser may assume Style A. |
| **Eligible** | A repository that has the configured `api_ref_path` (`api-ref/source`) and therefore becomes a `Service`. |
| **Excluded document** | A path skipped by configuration (`excluded_segments`, e.g. `out-of-date_apis`). Recorded in `excluded_documents` — skipping is a decision, so it is written down. |
| **Truncated listing** | The provider returned a capped file tree. Surfaces as `FileListing.truncated` and fails the repository scan (`error`) — a capped tree means the pinned snapshot was never read in full. |
| **Repository context** | Shared definitions resolved across a repository's documents before parsing individual files, so cross-file references can be followed. |

## Parser-internal vocabulary

Defined in `src/tools/scanner/parsers/docutils/types.py`. These never leave the
parser and are not part of any serialized contract - they are listed here
because two of them sit uncomfortably close to contract names.

| Name | Meaning |
|---|---|
| `SectionKind` | The role of a top-level heading inside an RST document: `uri`, `request`, `response`, `example_request`, `example_response`, `example_combined`, `status_codes`, `function`, `other`. |
| `TableTarget` | Where a parsed table is routed when it is not an endpoint section: `nested_struct`, `generic_request`, `intentionally_ignored`, `unmapped`. |
| `DocStyle` | Layout classification of a document: `style_a`, `s3_compatible`, `not_endpoint`. |

**`SectionName` is not `SectionKind`.** `SectionName` is the contract: the seven
sections every `Endpoint` carries. `SectionKind` is the parser's reading of a
heading in the source document, and it deliberately has members that are not
sections at all (`function`, `status_codes`, `other`). Translating one into the
other is the parser's job. Using one where the other belongs is a bug no type
checker will catch, because both are `str` enums and both will compare happily
against a bare string.
