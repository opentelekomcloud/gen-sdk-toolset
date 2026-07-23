import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { keys } from "./queries";
import { CONFIG } from "../constants";
import type { ExcludeRequest, RescanRequest, RescanResponse, RollbackResponse, ServiceDetail } from "./types.local";

/**
 * The full invalidation set (PS11/PS14): a completed scan, a rollback, or an
 * exclusion changes the generation or the working set — service detail,
 * documents, cached document details, services list, summary, and attention
 * are all stale together.
 */
export function invalidateGeneration(qc: QueryClient, name: string) {
  void qc.invalidateQueries({ queryKey: keys.service(name) });
  void qc.invalidateQueries({ queryKey: keys.documents(name) });
  void qc.invalidateQueries({ queryKey: keys.documentDetails(name) });
  void qc.invalidateQueries({ queryKey: keys.services() });
  void qc.invalidateQueries({ queryKey: keys.summary });
  void qc.invalidateQueries({ queryKey: keys.attention });
}

export function useRescan(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<RescanResponse>(`/scan/services/${encodeURIComponent(name)}/rescan`, {
        method: "POST",
        body: JSON.stringify({ initiated_by: CONFIG.identity } satisfies RescanRequest),
      }),
    /* optimistic: the service flips to scanning immediately (PS14) */
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: keys.service(name) });
      const prev = qc.getQueryData<ServiceDetail>(keys.service(name));
      if (prev) {
        qc.setQueryData<ServiceDetail>(keys.service(name), {
          ...prev,
          scan_status: "scanning",
          started_by: CONFIG.identity,
          started_at: new Date().toISOString(),
        });
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      /* incl. 409 already-scanning: roll the optimistic state back, re-sync */
      if (ctx?.prev) qc.setQueryData(keys.service(name), ctx.prev);
      void qc.invalidateQueries({ queryKey: keys.service(name) });
      void qc.invalidateQueries({ queryKey: keys.services() });
    },
    onSuccess: (res) => {
      /* TODO: useJob(res.job_id) polls to completion, then calls
         invalidateGeneration(qc, name). Check polling policy. */
      const cur = qc.getQueryData<ServiceDetail>(keys.service(name));
      if (cur?.scan_status === "scanning" && !cur.job_id) {
        qc.setQueryData<ServiceDetail>(keys.service(name), { ...cur, job_id: res.job_id });
      }
      void qc.invalidateQueries({ queryKey: keys.services() });
      void qc.invalidateQueries({ queryKey: keys.summary });
    },
  });
}

export function useRollback(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<RollbackResponse>(`/scan/services/${encodeURIComponent(name)}/rollback`, { method: "POST" }),
    onSettled: () => invalidateGeneration(qc, name),
  });
}

export function useExclude(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) =>
      apiFetch<void>(`/scan/services/${encodeURIComponent(name)}/exclude`, {
        method: "POST",
        body: JSON.stringify({ reason, initiated_by: CONFIG.identity } satisfies ExcludeRequest),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.excluded });
      invalidateGeneration(qc, name);
    },
  });
}

export function useInclude(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>(`/scan/services/${encodeURIComponent(name)}/include`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.excluded });
      invalidateGeneration(qc, name);
    },
  });
}
