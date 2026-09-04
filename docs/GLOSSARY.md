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
the `Unknown` fallback. Documentation writes several names for the same type -
`int64` and `Long`, `dict` and `Dictionary` - and `field_type.py::_ALIASES` maps
each spelling onto one of these values, matched whole and case-insensitively.
That table holds **conventions, never corrections**: `Interger` stays `Unknown`
and raises `UNKNOWN_TYPE_FORMAT`, because absorbing a typo would turn a defect
the panel counts into a field that looks read.

The forms that carry a structure name - `List<Node>`, `Map<String, Node>`,
`Schedule data structure`, `Node structure array` - cannot be a table of
spellings, so `field_type.py::_normalize_named_syntax` rewrites them into the
prose the classifier already reads (`Array of Node objects`, `Object`,
`Schedule object`). One set of rules therefore decides every type, and
`List<String>` lands on `Array of strings` for the same reason the prose
spelling does. `List` and `Map` are **not** IR types and must not become any:
the names they carry survive in `type_name`, and a `Map`'s key and value types
do not survive at all, because there is nowhere in the IR to put them.

A **structure name** is one identifier that is not already a type
(`field_type.py::_names_a_structure`, which asks `classify_type` rather than
listing the type words a second time). Both halves are load-bearing:
`Specifies the schedule data structure` is prose, and `List data structure`
names an array, so neither is rewritten and both read exactly as they did
before. What the rewrite does not recognize stays `Unknown` and is counted,
which is the answer this project would rather have than a confident `Object`
pointing at a structure called "List".

A container the rewrite does not know - `List<Set<Node>>` - keeps its array type
and reports no name, rather than one spelled `Set<Node>`. What `type_name` holds
for the forms that already existed is unchanged; `Array of booleans` still
leaves "booleans" behind, which is a separate question from this one.

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
removed from `RepositoryScanResult`, the `Snapshot` DB column, and the
frontend snapshot badge: every scenario that used to set it (a truncated
file listing) now fails the whole scan via `error` instead, so the field had
no remaining producer anywhere in the scanner.

The field counters on `SectionScanResult` must reconcile:
`fields_recognized + fields_unknown_type + fields_failed == fields_total`.

**`missing` is a fact about the document; `failed` is a fact about us.** A
section is `missing` only when the document does not contain it. A section whose
content we saw and could not read is `failed`, carrying the diagnostic that says
what was left unread (`UNMAPPED_TABLE` for a table, `UNMAPPED_BLOCK` for a code
block). Without that distinction "we never looked here" is indistinguishable
from "there is nothing here", which is the one confusion this project cannot
afford: it turns a silent loss into a clean number.

## Derived analytics

Defined in `src/tools/panel/core/analytics/`. Nothing here is stored in the scan
snapshot - it is computed from it, in one place, by the panel. The scanner emits
data only.

| Name | Where | Meaning |
|---|---|---|
| `OverallStatus` | `analytics/quality.py` | Document-level roll-up: `ok`, `partial`, `failed`, `unsupported`. `unsupported` specifically means the document style was not recognized. |
| `UNVERSIONED_KEY` (`"unversioned"`) | `analytics/quality.py` | The `by_version` bucket for an endpoint whose `api_version` could not be read from its URI or path. A real bucket, not an error. |
| `document_sections`, `doc_all_issues` | `analytics/quality.py` | The two per-document primitives the roll-ups are built from: the sections that were actually scanned, and every diagnostic on a document flattened with a section-prefixed location. |
| `assemble_nesting_from_examples`, `example_documentation_issues` | `analytics/assemble.py`, `analytics/validate.py` | On-demand example-driven views: rebuild the nesting an example proves, and flag where documentation and example disagree. |

The roll-ups themselves live in `analytics/snapshot.py` (`document_status`,
`analyze_document`, `analyze_snapshot`, `SnapshotAnalytics`) — see the panel
section below. One number has one definition: there is no second set of
roll-ups anywhere else.

Organization-level reporting is **not** part of the scanner. The panel owns
organization orchestration, because that is where the job state making it
resumable across rate limits lives.

### What ingest computes (panel-owned)

Defined in `src/tools/panel/core/analytics/snapshot.py`. Pure functions over
the IR — they own no state and no persistence; `ingest_service_result` writes
what they return into the existing `snapshot` and `document` rows. The
document-level primitives above (`document_sections`, `doc_all_issues`,
`OverallStatus`, `UNVERSIONED_KEY`) come from the sibling `quality.py`.

| Name | Meaning |
|---|---|
| `completeness` | The recognized share of the documented parameter rows: `fields_recognized / fields_total`, a `0..1` float. Per document it covers that document's sections; per `Snapshot` it is **field-weighted** over all documents, not a mean of per-document means. |
| `DocumentAnalytics` | What one `DocumentRecord` stores beyond its payload: `overall_status`, `completeness`, `issues_count`. |
| `SnapshotAnalytics` | The `Snapshot` roll-up: the counters that have columns, plus `unknown_count`, `fields_total`, `fields_recognized`, `by_section_status`, `issues_by_code` and `by_version`. Serialized whole into the `analytics` JSONB. |
| `SCANNER_GAP_CODES` | The diagnostics that describe **our** shortfall rather than the documentation's: `UNMAPPED_BLOCK`, `PARSER_ERROR`, `UNSUPPORTED_DOC_STYLE`, `FETCH_FAILED`. They make the scan `partial` and are excluded from `docs_ok` - the pages may be perfectly fine. |
| `unread_documents` | Documents carrying at least one scanner-gap diagnostic. This is what makes a service `partially scanned`. |
| `documentation_clean` | Documents with no diagnostic about the documentation itself (scanner gaps do not count). The numerator of `docs_ok`. |
| `unknown_count` | Documents with no derivable `OverallStatus` (a successfully scanned non-endpoint page). It exists so that `ok + partial + failed + unsupported + unknown == documents_total` — without it the difference would be unexplained. |

**Unmeasurable is `None`, never `0`.** A document whose structure could not be
measured — a plain page, or one gated before any table was read — has
`completeness = NULL`, and so does a `Snapshot` with no measurable fields.
Reporting `0.0` would claim we measured it and found nothing, which is a
different fact. Both columns are nullable for exactly this reason.

`issues_by_code` counts **every** code, not a top-N slice: a truncated map
stored as the whole truth is a silent loss. Callers that want the top five take
them at read time.

## Panel — the persisted model

Defined in `src/tools/panel/core/db/models.py`. Note the name collision and mind
it: `Service` here is a database row, not the IR entity above.

**Snapshot, and the word that is no longer available.** A `Snapshot` is the
persisted result of one repository scan at one commit — the thing the panel
lists, activates and rolls back. It was called `Generation` until the rename;
nothing about its behaviour changed, only its name.

The word **generation** is now reserved for **SDK code generation** — the Phase 3
generator that emits Python files. Three things legitimately still carry it, and
none of them is a scan result: `JobKind.generate` (the future code-generation
job, alongside `scan` and `maintain`), the frontend's `tab.generation` panel, and
prose about what a generator can build from a document. If you are naming
something that holds or describes a scan result, it is a snapshot; if it emits or
describes emitted code, it is a generation.

| Name | Meaning |
|---|---|
| `Service` (table `service`) | A tracked repository, keyed by the unique `repo`. Holds eligibility, discovery state, and pointers to its active and latest `Snapshot`. |
| `ExcludedService` | A `Service` deliberately excluded, with `reason` and `excluded_by`. |
| `Snapshot` | One ingested scan: `branch`, `commit_hash`, `scanner_version`, `document_schema_version`, the roll-up counters and `analytics`. |
| `DocumentRecord` (table `document`) | One document inside a `Snapshot`: the full IR `payload` plus the columns denormalized for querying. |
| `RepositoryScanJob` (table `job`) | One scan run: `kind`, `status`, `initiated_by`, timestamps, `error`, `interruption`. |
| `JobKind`, `JobStatus` | `JobStatus` is `queued`, `running`, `done`, `failed`. |
| `TERMINAL_JOB_STATUSES` | `done` and `failed` — the statuses nothing may move a Job out of. Cancellation and the background runner both test against it, so "may I still change this Job?" has one answer. |
| `terminate_job(job_id, reason)` | `panel/core/jobs.py`. Ends a non-terminal Job now: `failed`, `error = reason`, `finished_at = now()`. Returns whether *this* call ended it, so a caller can tell "cancelled" from "was already finished" without re-reading the row. Terminal Jobs are left exactly as they are. |
| **Termination is database-only** | `BackgroundTasks` runs the scan in a worker thread that cannot be cancelled from outside, so a scan in flight runs to completion. What is guaranteed is that the Job is closed and the result never persisted: the runner re-checks the Job before ingesting, and ingest locks the row and refuses a Job that is not `running`. There is deliberately **no** `cancelled` status — a terminated Job is `failed` with the reason in `error`, so every consumer that already handles failure handles this, and no status is added that nothing would ever produce. |
| **Cancel** | `POST /api/jobs/{id}/cancel` → `terminate_job(id, "cancelled by user")`. `404` unknown, `409` when the Job already finished (not a silent no-op), otherwise the terminated Job. |
| **Activate** | `POST /api/scan/services/{repo}/snapshots/{snapshot_id}/activate` (body `initiated_by`) → the same `SnapshotsResponse` the picker lists. Sets `Service.active_snapshot_id` and nothing else, so every view downstream (detail, documents, summary, attention, export) follows the pointer while `latest_snapshot_id` and the stored Snapshots stay put. `404` for an unknown Service or a Snapshot that is not this Service's; `409` while a scan Job is queued or running, whatever the request would change, because ingest moves the same pointer (`TERMINAL_JOB_STATUSES` never block). Re-activating the active Snapshot is a `200` that changes nothing, and an excluded Service is allowed. `initiated_by` is logged and **not persisted** — there is no activation audit trail. |
| **Snapshot deduplication** | Ingest stores a new `Snapshot` only when `commit_hash`, `scanner_version` or the serialized `analytics` differs from `Service.latest_snapshot`; otherwise the Job completes `done` against the existing row and no `Snapshot` or `DocumentRecord` is written. So the history counts changes in the result, not rescans. The denormalized counter columns are projections of `analytics` and are not compared separately, and document payloads are never compared — at an identical commit and scanner version they cannot differ. Compared against `latest_snapshot`, never `active_snapshot`: active is a display choice an operator may have pinned to an older entry. |
| `Snapshot.created_at` / `Snapshot.last_scanned_at` | `created_at` is when this result first appeared; `last_scanned_at` is when a successful scan last reproduced it. Equal on a new Snapshot, and moved forward by every unchanged rescan — the only mark such a scan leaves, since it stores no Snapshot of its own. The pair reads as "this result held from `created_at` and was still true at `last_scanned_at`". `ServiceListItem.scanned_at` is `latest_snapshot.last_scanned_at`, which is the last successful scan on both ingest paths: a changed result makes a new latest, an unchanged one bumps the existing latest. |
| `RepositoryScanJob.result_snapshot_id` | The `Snapshot` a Job's result is represented by — the one it created, or the reused latest one. Nullable (a failed or unfinished Job has none) and shared by many Jobs, unlike `Snapshot.source_job_id`, which is unique and names only the Job that first produced the row. `JobResponse.scanner_version` and `commit_hash` are served from here, so an unchanged rescan still reports the commit it read. |
| `Service.has_api_ref` | Tri-state. `NULL` = discovery has never checked this repository (where every hand-registered service starts); `false` = checked, no API-reference path; `true` = eligible. The column is nullable with **no** default, so a row cannot land on `false` without a check having produced it. |
| **Ineligible repository** | A `Service` with `has_api_ref IS FALSE`. Stored rather than skipped, so "looked at, found nothing" is a recorded result instead of a line of CLI output. Filtered out of `_service_query()` — which removes it from the registry, `/scan/summary` and `/scan/attention` — and served by `GET /api/scan/ineligible` (`repo`, `name`, `branch`, `checked_at`, ordered by `repo`). `start_scan` and `exclude` both refuse one with `409`. Every filter and guard tests `IS FALSE`, never falsiness: a `NULL` service stays listed, scannable and excludable. |
| **Demotion guard** | Discovery will not set `has_api_ref = False` on a `Service` that already has a `Snapshot` or an exclusion row; it logs a warning and keeps the current value. One empty lookup is not proof the documentation is gone — a moved default branch or a renamed path reads the same — and demoting would drop the row out of the registry along with a scan history nothing else links to. |
| **Exclude / Include** | `POST /api/scan/services/{repo}/exclude` (body `reason`, `initiated_by`) and `POST .../include`, both `204`. `404` unknown service, `422` blank reason or initiator, `409` already excluded / not excluded — a restore that changes nothing is not a silent success. Exclusion is non-destructive: no Job, Snapshot or document row is touched, so a restored `Service` returns with the history it had. `include` deletes the `ExcludedService` row rather than archiving it, so the reason text lives exactly as long as the exclusion does. |
| **Where exclusion is enforced** | Filtered out in `_all_services()` (`api/routes/scan_read.py`), which is what the registry, `/scan/summary` and `/scan/attention` are all built from — one decision, so the table and the header counters cannot disagree. Deliberately **not** in `_service_query()`: the detail endpoints keep answering for an excluded `Service`, or the UI could never load the page that restores it. `start_scan` refuses an excluded `Service` with `409`; it and `exclude` both take a `with_for_update()` lock on the `Service` row, because the two writes touch different tables and no unique index would catch them racing. A Job already queued or running when the exclusion lands is left alone and ingests normally — exclusion applies from the next launch. |
| **Scheduled discovery** | `panel discover` run by a cron entry on the host as the `discovery` compose service, which sits behind the `sync` profile so `up` never starts it (`staging/README.md` has the line). One pass upserts the registry, refreshes `eligibility_checked_at` and re-reads each eligible repository's branch HEAD, so drift marks stay current without anyone running the CLI. It creates **no** `RepositoryScanJob`: a scan is an operator's decision, never a schedule's. An interruption keeps what the pass already wrote and exits non-zero — nothing retries inside a run; the next run finishes the work. |
| `PanelRole` | `worker` or `viewer` (`panel/api/auth.py`), the role keys as granted in Zitadel. `worker` may launch and cancel scans, activate a Snapshot and exclude or include a Service; `viewer` may read. `worker` is a superset of `viewer`, so a token needs only the one role. |
| `Identity` | Who made a request: `subject` (the token's `sub`), `name` and the granted roles. `name` is what is written to `job.initiated_by` and `ExcludedService.excluded_by`, and it comes from **userinfo**, not from the token: Zitadel's claims matrix asserts `preferred_username`, `name` and `email` in the ID token and at `{issuer}/oidc/v1/userinfo`, never in an access token, so reading them off the bearer token would record a numeric subject for everybody. Resolved once per subject and cached for 15 minutes; a claim already on the token (which a Zitadel action can add) wins and costs no call; an unreachable userinfo falls back to the subject with a warning rather than failing the request. The request body still carries `initiated_by` and it is still ignored — a self-reported name is not an attribution. |
| **Authentication** | Every route under `/api` requires a valid Zitadel OIDC bearer token; `/health` does not, because the container healthcheck holds none. Applied to the whole prefix so a new route is closed by default; the five mutations additionally depend on `require_worker`. Signature, issuer, audience and expiry are checked against the JWKS at `{issuer}/oauth/v2/keys`, fetched on the first request and refetched once on an unknown `kid`. Missing or invalid token → `401` with a `WWW-Authenticate` challenge; a valid token without `worker` on a mutation → `403`; a valid token carrying neither panel role → `401`, because its holder is not a principal here at all. An unconfigured panel (no `AUTH__ISSUER` / `AUTH__AUDIENCE`) answers `500`: nobody could hold a token that would work, so it is the operator's problem, not the caller's. |
| **Startup cleanup** | The API's lifespan hook calls `terminate_orphaned_jobs()`, ending every Job left `queued` or `running` by a previous process with `"interrupted by panel restart"`. Without it an orphan blocks its service forever through `uq_active_scan_job_per_service`. |
| `HealthResponse.status` | `ok` or `degraded` (`api/routes/health.py`). `degraded` means the panel is serving but knows it is missing a capability — today only that startup cleanup could not reach the database, so some services may refuse a rescan until their Job is cancelled. It still answers `200`: the container healthcheck polls this, and failing it would stop the frontend from starting over a janitorial problem. Only expected operational failures degrade; a defect in the cleanup stops startup instead of no-opping every boot. |
| `IngestRejected` | `panel/core/ingest.py`. The Job or the scan result did not satisfy the successful-ingest contract (not a running scan Job, a failed or commit-less result, a repository that is not a `Service`, or a repository mismatch). The scan runner turns it into a `failed` Job with the message recorded. |

### Derived service state (what the read endpoints serve)

Defined in `src/tools/panel/core/service_state.py`. Computed from a Service's
jobs and snapshots on every read - never stored, so it cannot go stale.

| Name | Meaning |
|---|---|
| `ScanStatus` | How completely **we** read the service, never how good its documentation is: `scanning` (a queued or running scan job), `not_scanned` (no snapshot, no failure), `failed` (no snapshot and the last job failed), `partial` (something stayed unread - a document we could not interpret at all, or parameter rows we could not recognize), `scanned` (everything was read, however messy it turned out to be). |
| `RescanReason` | Why the panel suggests a rescan, in priority order: `retry` (the last job failed), `partial` (documents came out partial or failed), `version` (an older scanner produced the snapshot), `drift` (`head_commit` differs from the scanned commit). At most one is reported. |
| Attention rules | The same four codes (`failed`, `version`, `drift`, `new`) evaluated **independently** for the app-level band: a service can appear under several, because hiding one behind another would understate the work. `new` means never scanned and never failed. |
| `status_documents` | Documents that carry a status - the sum of the overall breakdown, and what the UI calls `documents`. Pages that are not API documents are reported as `non_endpoint_documents` (the snapshot analytics' `unknown_count`), never folded into a status. |
| `docs_ok` (`clean_endpoint_share`) | **Documentation quality**: how much of the documentation a generator can use, `0..1`. Documents are **weighted**, not counted - clean `1`, degraded `0.5`, uninterpretable `0` - so "half the endpoints are partial" stops reading like "half are unusable". `None` when nothing carries a status: unknown, not zero. |
| `EXAMPLE_SECTIONS` | `example_request`, `example_response`. Diagnostics found there (invalid JSON, an unread example block) stay visible on the document and in the issue filters but move **no** quality number: a generator builds from the parameter tables, so a broken example says nothing about whether the endpoint can be generated. Decided with the team on 2026-07-29. |
| `document_status` | The panel's document roll-up, and the only one: judged on the material sections only, so an example defect never degrades it. |

Two numbers answer two different questions and must not be swapped: `docs_ok`
measures the documentation, `Snapshot.completeness` measures our parser (the
share of documented parameter rows it understood). The snapshot selector shows
both side by side for exactly that reason.

Note the two different meanings of "non-endpoint": the `snapshot.non_endpoint_documents`
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
