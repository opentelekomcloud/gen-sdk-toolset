/**
 * Contract types (PS1 + PS15).
 * TEMPORARY — once openapi.json covers /scan (PS1/PS15), delete this file
 * and import from `src/shared/api/schema.gen.ts` (`components['schemas'][…]`) instead. Shapes mirror the contracts
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
  /* present while scan_status === "scanning" */
  job_id?: string;
  started_by?: string;
  started_at?: string;
}

export interface ServicesResponse {
  items: ServiceListItem[];
  /** One entry per ServiceFilter value; computed with q applied, status ignored. */
  counts: Record<ServiceFilter, number>;
}

export interface ServiceDetail extends ServiceListItem {
  has_previous: boolean;
  top_issues: IssueCount[];
  non_endpoint_documents: number;
}

export interface DocumentListItem {
  id: string;
  method: string | null;
  uri: string | null;
  title: string | null;
  document: string;
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
  id: string;
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
  job_id: string;
}

export interface RollbackResponse {
  current_job_id: string;
  previous_job_id: string;
  scanned_at: string;
  scanner_version: string;
}

export interface ExcludeRequest {
  reason: string;
  initiated_by: string;
}

export interface ApiErrorEnvelope {
  error: { code: string; message: string };
}
