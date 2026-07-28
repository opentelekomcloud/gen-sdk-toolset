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

### What ingest computes (panel-owned)

Defined in `src/tools/panel/core/analytics/generation.py`. Pure functions over
the IR — they own no state and no persistence; `ingest_service_result` writes
what they return into the existing `generation` and `document` rows. The
document-level functions above are imported from `tools.domain` until issue #34
relocates them.

| Name | Meaning |
|---|---|
| `completeness` | The recognized share of the documented parameter rows: `fields_recognized / fields_total`, a `0..1` float. Per document it covers that document's sections; per `Generation` it is **field-weighted** over all documents, not a mean of per-document means. |
| `DocumentAnalytics` | What one `DocumentRecord` stores beyond its payload: `overall_status`, `completeness`, `issues_count`. |
| `GenerationAnalytics` | The `Generation` roll-up: the counters that have columns, plus `unknown_count`, `fields_total`, `fields_recognized`, `by_section_status`, `issues_by_code` and `by_version`. Serialized whole into the `analytics` JSONB. |
| `unknown_count` | Documents with no derivable `OverallStatus` (a successfully scanned non-endpoint page). It exists so that `ok + partial + failed + unsupported + unknown == documents_total` — without it the difference would be unexplained. |

**Unmeasurable is `None`, never `0`.** A document whose structure could not be
measured — a plain page, or one gated before any table was read — has
`completeness = NULL`, and so does a `Generation` with no measurable fields.
Reporting `0.0` would claim we measured it and found nothing, which is a
different fact. Both columns are nullable for exactly this reason.

`issues_by_code` counts **every** code, not a top-N slice: a truncated map
stored as the whole truth is a silent loss. Callers that want the top five take
them at read time.

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
| `IngestRejected` | `panel/core/ingest.py`. The Job or the scan result did not satisfy the successful-ingest contract (not a running scan Job, a failed or commit-less result, a repository that is not a `Service`, or a repository mismatch). The scan runner turns it into a `failed` Job with the message recorded. |

### Derived service state (what the read endpoints serve)

Defined in `src/tools/panel/core/service_state.py`. Computed from a Service's
jobs and generations on every read - never stored, so it cannot go stale.

| Name | Meaning |
|---|---|
| `ScanStatus` | How completely **we** read the service, never how good its documentation is: `scanning` (a queued or running scan job), `not_scanned` (no generation, no failure), `failed` (no generation and the last job failed), `partial` (something stayed unread - a document we could not interpret at all, or parameter rows we could not recognize), `scanned` (everything was read, however messy it turned out to be). |
| `RescanReason` | Why the panel suggests a rescan, in priority order: `retry` (the last job failed), `partial` (documents came out partial or failed), `version` (an older scanner produced the generation), `drift` (`head_commit` differs from the scanned commit). At most one is reported. |
| Attention rules | The same four codes (`failed`, `version`, `drift`, `new`) evaluated **independently** for the app-level band: a service can appear under several, because hiding one behind another would understate the work. `new` means never scanned and never failed. |
| `status_documents` | Documents that carry a status - the sum of the overall breakdown, and what the UI calls `documents`. Pages that are not API documents are reported as `non_endpoint_documents` (the generation analytics' `unknown_count`), never folded into a status. |
| `docs_ok` (`clean_endpoint_share`) | **Documentation quality**: the share of documents scanned without a single diagnostic. A section leaves `ok` exactly when something in the document was wrong, so this needs no thresholds and no issue-code classification. `None` when nothing carries a status - unknown, not zero. |

Two numbers answer two different questions and must not be swapped: `docs_ok`
measures the documentation, `Generation.completeness` measures our parser (the
share of documented parameter rows it understood). The generation selector shows
both side by side for exactly that reason.

Note the two different meanings of "non-endpoint": the `generation.non_endpoint_documents`
**column** counts everything that is not a parsed endpoint (including failed and
unsupported documents), while the API's `non_endpoint_documents` **field** counts
only the pages with no scan status at all. The API serves the second one, because
that is the number the UI puts next to "documents".

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
