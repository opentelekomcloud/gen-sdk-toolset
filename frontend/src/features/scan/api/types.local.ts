/**
 * Contract types (PS1 + PS15 + G1 generations).
 * TEMPORARY — once openapi.json covers /scan, delete this file and import from
 * `src/shared/api/schema.gen.ts` instead. Shapes mirror the DTOs the panel API
 * builds from the persistence models (service / job / generation / document),
 * so the swap is mechanical.
 */

export type ScanStatus = "scanned" | "partial" | "failed" | "not_scanned" | "scanning";
export type DocStatus = "ok" | "partial" | "failed" | "unsupported";
export type SectionStatus = "ok" | "partial" | "failed" | "skipped" | "missing";
/** Priority order: retry → partial → version → drift (computed server-side). */
export type RescanReason = "retry" | "partial" | "version" | "drift";
export type Section =
  | "path_params"
  | "query_params"
  | "headers"
  | "body"
  | "response"
  | "example_request"
  | "example_response";
export type AttentionRuleCode = "failed" | "version" | "drift" | "new";
export type PanelName = "scan" | "generation" | "maintenance";
/** Mirrors JobKind / JobStatus enums on the `job` table. */
export type JobKind = "scan" | "generate" | "maintain";
export type JobStatus = "queued" | "running" | "done" | "failed";

export type ServiceFilter = "all" | ScanStatus | "needs_rescan";
export type ServiceSort = "quality" | "docs" | "name";

export interface IssueCount {
  code: string;
  count: number;
}

export interface SectionCounts {
  ok?: number;
  partial?: number;
  failed?: number;
  skipped?: number;
  missing?: number;
}

/**
 * G1: one immutable successfully persisted scan snapshot — DTO of the
 * `generation` table (a failed job creates no generation). `created_at` is
 * the scan timestamp; `completeness` is a 0..1 float — use lib/generation.ts
 * helpers for percent and short commit display.
 */
export interface Generation {
  id: number;
  source_job_id: number;
  branch: string;
  /** Full commit hash the scan ran against (shorten in UI via shortCommit). */
  commit_hash: string;
  scanner_version: string;
  document_schema_version: string;
  /** Set when the scan finished but could not cover everything. */
  incomplete_reason: string | null;
  documents_total: number;
  endpoints_total: number;
  non_endpoint_documents: number;
  issues_total: number;
  ok_count: number;
  partial_count: number;
  failed_count: number;
  unsupported_count: number;
  /** 0..1, nullable (e.g. no endpoint documents). */
  completeness: number | null;
  created_at: string;
}

export interface GenerationsResponse {
  /** Newest first (ix_generation_service_created_at DESC). */
  items: Generation[];
  /** Mirror Service.active_generation_id / latest_generation_id — nullable in the DB. */
  active_id: number | null;
  latest_id: number | null;
}

export interface ActivateGenerationRequest {
  initiated_by: string;
}

/** Mirrors RepositoryInterruptionKind — typed operational failure on the job. */
export type RepositoryInterruptionKind = "rate_limit" | "authentication" | "permission_denied" | "repository_failure";

export interface RepositoryInterruption {
  kind: RepositoryInterruptionKind;
  repository: string | null;
  message: string;
  /** Unix seconds when the rate limit resets (rate_limit only). */
  reset_time: number | null;
}

export interface ServiceListItem {
  name: string;
  scan_status: ScanStatus;
  documents: number | null;
  struct_ok: number | null;
  scanner_version: string | null;
  scanned_at: string | null;
  docs_changed: boolean;
  rescan_reason: RescanReason | null;
  overall_breakdown: Partial<Record<DocStatus, number>>;
  section_rollup: Record<Section, SectionCounts>;
  error: string | null;
  /* present while scan_status === "scanning" — from the queued/running job */
  job_id?: number;
  initiated_by?: string | null;
  started_at?: string;
}

export interface ServicesResponse {
  items: ServiceListItem[];
  /** One entry per ServiceFilter value; computed with q applied, status ignored. */
  counts: Record<ServiceFilter, number>;
}

export interface ServiceDetail extends ServiceListItem {
  /**
   * G1: snapshot currently displayed / served (Service.active_generation).
   * Null when no successful scan exists yet. All flat scan-result fields on
   * this DTO (documents, struct_ok, overall_breakdown, section_rollup,
   * top_issues, …) are served FROM this generation.
   */
  active_generation: Generation | null;
  /** G1: newest persisted snapshot (Service.latest_generation) — may deliberately differ from active. */
  latest_generation: Generation | null;
  /**
   * Service.head_commit — current HEAD of the docs repo; drift =
   * head_commit !== active_generation.commit_hash (docs_changed is the
   * server-computed shortcut for exactly that).
   */
  head_commit: string | null;
  /** Structured operational failure from the last failed job (job.interruption JSONB); null when error is a plain scan error. */
  interruption: RepositoryInterruption | null;
  top_issues: IssueCount[];
  non_endpoint_documents: number;
}

export interface DocumentListItem {
  /** document.id (int PK). */
  id: number;
  method: string | null;
  uri: string | null;
  title: string | null;
  /** document.path — generated projection of payload->>'path'. */
  path: string;
  overall_status: DocStatus;
  issues: IssueCount[];
}

export interface DocumentsResponse {
  items: DocumentListItem[];
  total: number;
  page: number;
  page_size: number;
  /** Computed with q applied, status ignored (aligned with services counts). */
  doc_counts: Record<DocStatus | "all", number>;
}

export interface Parameter {
  name: string;
  param_type: string;
  mandatory: boolean;
  description: string;
  children?: Parameter[];
}

export interface SectionIssue {
  code: string;
  location?: string;
  details?: string;
}

export interface SectionDetail {
  name: Section;
  status: SectionStatus;
  fields_total: number;
  fields_recognized: number;
  fields_unknown_type: number;
  parameters: Parameter[] | null;
  issues: SectionIssue[];
}

export interface DocumentDetail {
  id: number;
  method: string | null;
  uri: string | null;
  title: string | null;
  api_version: string | null;
  overall_status: DocStatus;
  failure_reason: string | null;
  sections: SectionDetail[];
}

export interface Summary {
  scanner_version: string;
  last_scanned_at: string | null;
  services_total: number;
  failed_services: number;
  documents_total: number;
  scans_running: number;
}

export interface AttentionRule {
  code: AttentionRuleCode;
  panel: PanelName;
  label: string;
  count: number;
}

/** Backed by service.exclude_reason / excluded_by / excluded_at columns. */
export interface ExcludedService {
  name: string;
  reason: string;
  excluded_by: string;
  excluded_at: string;
}

export interface RescanRequest {
  initiated_by: string;
}

export interface RescanResponse {
  /** job.id (int PK). */
  job_id: number;
}

export interface ExcludeRequest {
  reason: string;
  initiated_by: string;
}

export interface ApiErrorEnvelope {
  error: { code: string; message: string };
}
