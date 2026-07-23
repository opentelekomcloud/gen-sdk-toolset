/** G1 display helpers over the Generation DTO (mirrors the `generation` table). */
import type { Generation } from "../api/types.local";

/** DB stores the full commit_hash (64); UI shows the git-style short form. */
export const shortCommit = (hash: string): string => hash.slice(0, 7);

/** `created_at` of a generation IS the scan timestamp (no separate scanned_at column). */
export const fmtGenAt = (iso: string | null | undefined): string =>
  iso ? iso.replace("T", " ").slice(0, 16) : "—";

/** DB `completeness` is a 0..1 float (nullable); UI speaks percent. */
export const structPct = (completeness: number | null): number | null =>
  completeness == null ? null : Math.round(completeness * 100);

/** Breakdown for OverallBar from the generation's persisted status counts. */
export const genBreakdown = (g: Generation) => ({
  ok: g.ok_count,
  partial: g.partial_count,
  failed: g.failed_count,
  unsupported: g.unsupported_count,
});

export const isLatest = (activeId: number | null, latestId: number | null): boolean =>
  activeId == null || latestId == null || activeId === latestId;
