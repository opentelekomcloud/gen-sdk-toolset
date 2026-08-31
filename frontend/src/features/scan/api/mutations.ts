import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { invalidateSnapshot, keys } from "./queries";
import { CONFIG } from "../constants";
import type {
  ActivateSnapshotRequest,
  ExcludeRequest,
  SnapshotsResponse,
  ScanRequest,
  ScanResponse,
  ServiceDetail,
} from "../../../shared/api/types";

export function useRescan(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<ScanResponse>(`/scan/services/${encodeURIComponent(name)}/rescan`, {
        method: "POST",
        body: JSON.stringify({ initiated_by: CONFIG.identity } satisfies ScanRequest),
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
      /* ScanJobWatcher (mounted by ServicePage, keyed by job_id) polls this
         job via useJob and refreshes the panel on the terminal edge; here we
         only record the job_id and refresh the list/summary views. */
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
 * G1: make another persisted snapshot active (moves Service.active_snapshot_id).
 * Replaces useRollback — rollback is activate(previous). Never triggers a scan;
 * only changes which snapshot every scan-result view is served from.
 * Server answers 409 while a scan job is queued/running for this service.
 */
export function useActivateSnapshot(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (snapshotId: number) =>
      apiFetch<SnapshotsResponse>(
        `/scan/services/${encodeURIComponent(name)}/snapshots/${snapshotId}/activate`,
        {
          method: "POST",
          body: JSON.stringify({ initiated_by: CONFIG.identity } satisfies ActivateSnapshotRequest),
        },
      ),
    onSettled: () => invalidateSnapshot(qc, name),
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
      invalidateSnapshot(qc, name);
    },
  });
}

export function useInclude(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>(`/scan/services/${encodeURIComponent(name)}/include`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.excluded });
      invalidateSnapshot(qc, name);
    },
  });
}
