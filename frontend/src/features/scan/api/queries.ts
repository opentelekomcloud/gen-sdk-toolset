import { useQuery, type QueryClient } from "@tanstack/react-query";
import { apiFetch, qs } from "./client";
import type {
  AttentionRule,
  AttentionRuleCode,
  DocStatus,
  DocumentDetail,
  DocumentsResponse,
  ExcludedService,
  GenerationsResponse,
  Job,
  JobStatus,
  ServiceDetail,
  ServiceFilter,
  ServiceSort,
  ServicesResponse,
  Summary,
} from "./types.local";

/** Central query-key registry — the invalidation sets in mutations.ts depend on it. */
export const keys = {
  services: (p?: object) => (p ? (["services", p] as const) : (["services"] as const)),
  service: (name: string) => ["service", name] as const,
  documents: (name: string, p?: object) => (p ? (["documents", name, p] as const) : (["documents", name] as const)),
  /** Prefix for all cached document details of a service — invalidation target. */
  documentDetails: (name: string) => ["document", name] as const,
  document: (name: string, id: number) => ["document", name, id] as const,
  /** G1: generation history of a service. */
  generations: (name: string) => ["generations", name] as const,
  job: (id: number) => ["job", id] as const,
  summary: ["summary"] as const,
  attention: ["attention"] as const,
  excluded: ["excluded"] as const,
};

/**
 * The full invalidation set (PS11/PS14/G1): a completed scan, a generation
 * activation, or an exclusion changes the active generation or the working
 * set — service detail, documents, cached document details, generations list,
 * services list, summary, and attention are all stale together.
 * Lives here (next to `keys`) so both mutations.ts and useService can use it
 * without an import cycle.
 */
export function invalidateGeneration(qc: QueryClient, name: string) {
  void qc.invalidateQueries({ queryKey: keys.service(name) });
  void qc.invalidateQueries({ queryKey: keys.documents(name) });
  void qc.invalidateQueries({ queryKey: keys.documentDetails(name) });
  void qc.invalidateQueries({ queryKey: keys.generations(name) });
  void qc.invalidateQueries({ queryKey: keys.services() });
  void qc.invalidateQueries({ queryKey: keys.summary });
  void qc.invalidateQueries({ queryKey: keys.attention });
}

export interface ServicesParams {
  status?: ServiceFilter;
  q?: string;
  sort?: ServiceSort;
  /** Attention-rule filter (PS18) — takes precedence over status server-side. */
  rule?: AttentionRuleCode;
}

export function useServices(params: ServicesParams) {
  return useQuery({
    queryKey: keys.services(params),
    queryFn: () => apiFetch<ServicesResponse>(`/scan/services${qs({ ...params })}`),
  });
}

export function useService(name: string) {
  /* Scan-completion refresh is owned by ScanJobWatcher (F8, useJob); this query
     just serves the service detail. */
  return useQuery({
    queryKey: keys.service(name),
    queryFn: () => apiFetch<ServiceDetail>(`/scan/services/${encodeURIComponent(name)}`),
  });
}

/** G1: lazy — call with enabled: open (popover); trigger renders from ServiceDetail.active_generation. */
export function useGenerations(name: string, enabled = true) {
  return useQuery({
    queryKey: keys.generations(name),
    queryFn: () => apiFetch<GenerationsResponse>(`/scan/services/${encodeURIComponent(name)}/generations`),
    enabled,
  });
}

export interface DocumentsParams {
  status?: DocStatus | "all";
  q?: string;
  page?: number;
}

export function useDocuments(name: string, params: DocumentsParams) {
  return useQuery({
    queryKey: keys.documents(name, params),
    queryFn: () =>
      apiFetch<DocumentsResponse>(
        `/scan/services/${encodeURIComponent(name)}/documents${qs({
          ...params,
          status: params.status === "all" ? undefined : params.status,
        })}`,
      ),
    placeholderData: (prev) => prev, // keep the table while paging
  });
}

/** Lazy — call with enabled: open (PS13); loading/error/retry come from query state. */
export function useDocumentDetail(name: string, id: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.document(name, id),
    queryFn: () => apiFetch<DocumentDetail>(`/scan/services/${encodeURIComponent(name)}/documents/${id}`),
    enabled,
    staleTime: Infinity, // immutable within a generation; invalidated on rescan/activate
  });
}

export function useSummary() {
  return useQuery({ queryKey: keys.summary, queryFn: () => apiFetch<Summary>("/scan/summary") });
}

export function useAttention() {
  return useQuery({ queryKey: keys.attention, queryFn: () => apiFetch<AttentionRule[]>("/scan/attention") });
}

export function useExcluded() {
  return useQuery({ queryKey: keys.excluded, queryFn: () => apiFetch<ExcludedService[]>("/scan/excluded") });
}

/** Terminal job statuses — polling stops here. */
export const JOB_TERMINAL: JobStatus[] = ["done", "failed"];

/** Polling cadence for a job query: stop once terminal, else poll every 1.5s. */
export function jobRefetchInterval(job: Job | undefined): number | false {
  return job && JOB_TERMINAL.includes(job.status) ? false : 1500;
}

/**
 * F8: poll GET /api/jobs/{id} while the job is non-terminal; stop once it
 * reaches done/failed. Pass undefined to disable (no active job).
 */
export function useJob(jobId: number | undefined) {
  return useQuery({
    queryKey: keys.job(jobId ?? -1),
    enabled: jobId != null,
    queryFn: () => apiFetch<Job>(`/jobs/${jobId}`),
    refetchInterval: (query) => jobRefetchInterval(query.state.data),
  });
}
