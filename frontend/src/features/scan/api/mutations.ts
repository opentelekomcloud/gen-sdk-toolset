import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { invalidateGeneration, keys } from "./queries";
import { CONFIG } from "../constants";
import type {
  ActivateGenerationRequest,
  ExcludeRequest,
  GenerationsResponse,
  RescanRequest,
  RescanResponse,
  ServiceDetail,
} from "./types.local";

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
          initiated_by: CONFIG.identity,
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

/**
 * G1: make another persisted generation active (moves Service.active_generation_id).
 * Replaces useRollback — rollback is activate(previous). Never triggers a scan;
 * only changes which snapshot every scan-result view is served from.
 * Server answers 409 while a scan job is queued/running for this service.
 */
export function useActivateGeneration(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (generationId: number) =>
      apiFetch<GenerationsResponse>(
        `/scan/services/${encodeURIComponent(name)}/generations/${generationId}/activate`,
        {
          method: "POST",
          body: JSON.stringify({ initiated_by: CONFIG.identity } satisfies ActivateGenerationRequest),
        },
      ),
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
