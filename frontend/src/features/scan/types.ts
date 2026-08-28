/**
 * What the scan UI knows that the generated schema does not carry: view models,
 * which will never be generated, and narrowings of fields the backend types as
 * `str` or as a bare object, which would be generated if it typed them as the
 * enums they already are. Each one below names the field it narrows.
 *
 * The contract shapes themselves come from `shared/api/types.ts`.
 */
import type { ScanStatus } from "../../shared/api/types";

// --- Narrowings of loosely typed contract fields ---------------------------

/** `DocumentListItem.overall_status` - the four values its CHECK constraint
 *  allows. `doc_counts` is keyed by these plus `all`. */
export type DocStatus = "ok" | "partial" | "failed" | "unsupported";

/** `SectionDetail.status`. The scanner has four - ok, partial, failed, missing
 *  (`shared/scan/section.py`). `skipped` is the UI's own: it has a colour, a
 *  tone rule and a place in the tooltip, and no backend path produces it. */
export type SectionStatus = "ok" | "partial" | "failed" | "skipped" | "missing";

/** `SectionDetail.name`, and the keys of `section_rollup` - the seven members
 *  of `SectionName` (`shared/ir/section.py`). */
export type Section =
  | "path_params"
  | "query_params"
  | "headers"
  | "body"
  | "response"
  | "example_request"
  | "example_response";

/** One `section_rollup` entry: how that section came out across the snapshot. */
export type SectionCounts = Partial<Record<SectionStatus, number>>;

/** `AttentionRule.code` - the four rules `_ATTENTION_LABELS` names. */
export type AttentionRuleCode = "failed" | "version" | "drift" | "new";

/**
 * `ServiceDetail.interruption` - a structured operational failure recorded on
 * the last failed job. The backend stores it as a JSONB column and types the
 * field as a plain object, so the schema says only "an object"; this is the
 * shape it actually holds (`RepositoryInterruption`).
 */
type RepositoryInterruptionKind = "rate_limit" | "authentication" | "permission_denied" | "repository_failure";

export interface RepositoryInterruption {
  kind: RepositoryInterruptionKind;
  repository: string | null;
  message: string;
  /** Unix seconds when the rate limit resets (rate_limit only). */
  reset_time: number | null;
}

/**
 * The error body every failing route answers with. Produced by the exception
 * handlers rather than declared as a response model, so it is in no operation's
 * schema - see `panel/api/errors.py`.
 */
export interface ApiErrorEnvelope {
  error: { code: string; message: string };
}

// --- View models -----------------------------------------------------------

/** The registry's filter chips: every scan status, plus the two the UI adds. */
export type ServiceFilter = "all" | ScanStatus | "needs_rescan";
export type ServiceSort = "quality" | "docs" | "name";

/** What the documents block is narrowed to: a section's status, or an issue code. */
export type DocFilter =
  | { kind: "section"; section: Section; status: SectionStatus }
  | { kind: "issue"; code: string };
