import { useState } from "react";
import { useQuery, type QueryClient } from "@tanstack/react-query";
import { apiFetch, qs } from "./client";
import type {
  AttentionRule,
  DocumentDetail,
  DocumentsResponse,
  ExcludedService,
  Ineligible,
  SnapshotsResponse,
  ServiceDetail,
  ServicesResponse,
  Summary,
} from "../../../shared/api/types";
import type {
  AttentionRuleCode,
  DocStatus,
  Section,
  SectionStatus,
  ServiceFilter,
  ServiceSort,
} from "../types";

/** Central query-key registry — the invalidation sets in mutations.ts depend on it. */
export const keys = {
  services: (p?: object) => (p ? (["services", p] as const) : (["services"] as const)),
  service: (name: string) => ["service", name] as const,
  documents: (name: string, p?: object) => (p ? (["documents", name, p] as const) : (["documents", name] as const)),
  /** Prefix for all cached document details of a service — invalidation target. */
  documentDetails: (name: string) => ["document", name] as const,
  document: (name: string, id: number) => ["document", name, id] as const,
  /** G1: snapshot history of a service. */
  snapshots: (name: string) => ["snapshots", name] as const,
  summary: ["summary"] as const,
  attention: ["attention"] as const,
  excluded: ["excluded"] as const,
  ineligible: ["ineligible"] as const,
  /** Generation panel - served by features/generation/data/ from its in-memory mock. */
  genTargets: ["generation", "targets"] as const,
  genServices: ["generation", "services"] as const,
  genList: (p?: object) => (p ? (["generation", "list", p] as const) : (["generation", "list"] as const)),
  genResources: (name: string) => ["generation", "resources", name] as const,
  /** The layout of a service as the backend stores it. */
  genLayout: (name: string) => ["generation", "layout", name] as const,
  genAttention: ["generation", "attention"] as const,
  /** Prefix for the generation specs of every resource of a service — invalidation target. */
  genSpecs: (name: string) => ["generation", "spec", name] as const,
  genSpec: (name: string, resource: string) => ["generation", "spec", name, resource] as const,
  /** Mutation key of a service's layout edits; the edits that went through say it was edited. */
  genLayoutEdit: (name: string) => ["generation", "layout-edit", name] as const,
  /** The OTC tenant the panel's live calls go to - served from the Generation mock too. */
  otcSettings: ["settings", "otc"] as const,
};

/**
 * The full invalidation set (PS11/PS14/G1): a snapshot activation, an
 * exclusion or its undo changes the active snapshot or the working
 * set — service detail, documents, cached document details, snapshots list,
 * services list, summary, and attention are all stale together. So is the
 * Generation list (ADR-0077): the backend selects it by the active snapshot and
 * the exclusion, exactly what these events move, so it is fetched again rather
 * than patched here.
 * It serves only the tab that did the action; every other change - a scan
 * finishing included - arrives through the periodic refetch (ADR-0085).
 */
export function invalidateSnapshot(qc: QueryClient, name: string) {
  void qc.invalidateQueries({ queryKey: keys.service(name) });
  void qc.invalidateQueries({ queryKey: keys.documents(name) });
  void qc.invalidateQueries({ queryKey: keys.documentDetails(name) });
  void qc.invalidateQueries({ queryKey: keys.snapshots(name) });
  void qc.invalidateQueries({ queryKey: keys.services() });
  void qc.invalidateQueries({ queryKey: keys.summary });
  void qc.invalidateQueries({ queryKey: keys.attention });
  void qc.invalidateQueries({ queryKey: keys.genList() });
}

/**
 * An edit of a service's Generation layout changes its resources, and with
 * them what the list and the card count for it: `total`, and the state, when a
 * resource is made or goes - and the specs, whose operations are the endpoints
 * of a resource. Jobs are untouched, so the attention rules are not.
 */
export function invalidateGenLayout(qc: QueryClient, name: string) {
  void qc.invalidateQueries({ queryKey: keys.genLayout(name) });
  void qc.invalidateQueries({ queryKey: keys.genResources(name) });
  void qc.invalidateQueries({ queryKey: keys.genServices });
  void qc.invalidateQueries({ queryKey: keys.genSpecs(name) });
}

/**
 * A generation started for a resource gives it a job, and a merge picked up
 * from GitHub changes one: its resources carry the jobs, the list and the card
 * count them into the state of the service, and the attention rules count the
 * jobs in review and the failed ones. A refused start says the page was stale,
 * on the job, the layout or a field left to decide - so the specs, whose fields
 * carry the choices, are fetched again with the rest.
 */
export function invalidateGenJobs(qc: QueryClient, name: string) {
  void qc.invalidateQueries({ queryKey: keys.genResources(name) });
  void qc.invalidateQueries({ queryKey: keys.genServices });
  void qc.invalidateQueries({ queryKey: keys.genAttention });
  void qc.invalidateQueries({ queryKey: keys.genSpecs(name) });
}

/** What a block of the page shows of one query: its data, its failure, or that it is on the way. */
export interface Block<T> {
  /** The answer to show; undefined while the block has failed or is on the way. */
  data: T | undefined;
  /** The last request failed: the block shows that and a Retry instead of data. */
  failed: boolean;
  /** No answer and no failure yet: the first load is under way. */
  pending: boolean;
}

/**
 * The one rule every block follows for its query (ADR-0081).
 *
 * A request that failed is shown as a failure with a Retry, never as data:
 * TanStack Query keeps the last answer through a failed refresh, and that
 * answer would read as current. A first load that failed and a refresh that
 * failed look the same, and stay so while the periodic refresh (ADR-0076) or a
 * Retry asks again - for a query that never had an answer TanStack goes back
 * to "pending" on each new request, which would make the block disappear and
 * come back every 10 s. The block changes only when an answer arrives.
 */
export function blockOf<T>(query: {
  data: T | undefined;
  isError: boolean;
  isPending: boolean;
  errorUpdateCount: number;
}): Block<T> {
  const failed = query.isError || (query.isPending && query.errorUpdateCount > 0);
  return { data: failed ? undefined : query.data, failed, pending: !failed && query.isPending };
}

/** What a Retry needs of a query: TanStack's `refetch`. */
export interface Retryable {
  refetch: (options?: { cancelRefetch?: boolean }) => Promise<unknown>;
}

/**
 * A Retry the user asked for, and whether it is still under way.
 *
 * Only the click counts. The periodic refresh keeps asking for a query that
 * failed, every 10 s; shown as "loading", it would take the failure and its
 * Retry off the screen on each round and announce the failure again.
 *
 * A Retry clicked while that refresh is already asking joins it rather than
 * cancelling it for a second request: the backend has done the work for the
 * first, and refreshing may add no requests beyond the periodic one (ADR-0084,
 * ADR-0085). TanStack's own default would cancel and ask again.
 */
export function useRetry(query: Retryable) {
  const [retrying, setRetrying] = useState(false);
  const retry = () => {
    setRetrying(true);
    void query.refetch({ cancelRefetch: false }).finally(() => setRetrying(false));
  };
  return { retrying, retry };
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
  return useQuery({
    queryKey: keys.service(name),
    queryFn: () => apiFetch<ServiceDetail>(`/scan/services/${encodeURIComponent(name)}`),
  });
}

/**
 * G1: lazy — call with enabled: open (popover); trigger renders from ServiceDetail.active_snapshot.
 * `subscribed: enabled` makes a closed popover count as not shown, so its cache
 * is dropped like an unmounted page's and reopening loads from the server
 * (ADR-0078) - the component itself stays mounted while closed.
 */
export function useSnapshots(name: string, enabled = true) {
  return useQuery({
    queryKey: keys.snapshots(name),
    queryFn: () => apiFetch<SnapshotsResponse>(`/scan/services/${encodeURIComponent(name)}/snapshots`),
    enabled,
    subscribed: enabled,
  });
}

export interface DocumentsParams {
  status?: DocStatus | "all";
  q?: string;
  page?: number;
  /** Section filter — both halves or neither, mirroring the API. */
  section?: Section;
  section_status?: SectionStatus;
  /** Issue-code filter, from the top-issue chips. */
  issue?: string;
  /** One API version, or "unversioned". */
  api_version?: string;
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
    /* Keep the table while paging - but never from a request that failed: its
       rows are the stale answer the failure stands in for (ADR-0081), as for
       the Generation list. */
    placeholderData: (prev, prevQuery) => (prevQuery?.state.status === "error" ? undefined : prev),
  });
}

/**
 * Lazy — call with enabled: open (PS13); loading/error/retry come from query state.
 * `subscribed: enabled` drops the cache of a closed row, as for useSnapshots.
 */
export function useDocumentDetail(name: string, id: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.document(name, id),
    queryFn: () => apiFetch<DocumentDetail>(`/scan/services/${encodeURIComponent(name)}/documents/${id}`),
    enabled,
    subscribed: enabled,
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

export function useIneligible() {
  return useQuery({ queryKey: keys.ineligible, queryFn: () => apiFetch<Ineligible[]>("/scan/ineligible") });
}
