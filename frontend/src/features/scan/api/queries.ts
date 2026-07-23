import { useQuery } from "@tanstack/react-query";
import { apiFetch, qs } from "./client";
import type {
  AttentionRule,
  AttentionRuleCode,
  DocStatus,
  DocumentDetail,
  DocumentsResponse,
  ExcludedService,
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
  document: (name: string, id: string) => ["document", name, id] as const,
  summary: ["summary"] as const,
  attention: ["attention"] as const,
  excluded: ["excluded"] as const,
};

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
  return useQuery({
    queryKey: keys.service(name),
    queryFn: () => apiFetch<ServiceDetail>(`/scan/services/${encodeURIComponent(name)}`),
    /* while a scan job runs, poll so the page picks up completion (PS14 owns exact policy via useJob) */
    refetchInterval: (query) => (query.state.data?.scan_status === "scanning" ? 4000 : false),
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
export function useDocumentDetail(name: string, id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.document(name, id),
    queryFn: () => apiFetch<DocumentDetail>(`/scan/services/${encodeURIComponent(name)}/documents/${encodeURIComponent(id)}`),
    enabled,
    staleTime: Infinity, // immutable within a generation; invalidated on rescan/rollback
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
