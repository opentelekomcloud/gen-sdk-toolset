/** G1 display helpers over the Generation DTO (mirrors the `generation` table). */
import type { Generation } from "../api/types.local";

/** DB stores the full commit_hash (64); UI shows the git-style short form. */
export const shortCommit = (hash: string): string => hash.slice(0, 7);

const FMT_CACHE: Record<string, Intl.DateTimeFormat> = {};

/**
 * `created_at` of a generation IS the scan timestamp (no separate scanned_at
 * column). Rendered in the viewer's locale and timezone (en-GB: 23/07/2026,
 * 09:15 · de-DE: 23.07.2026, 09:15) — pass `locale` from useI18n().
 */
export const fmtGenAt = (iso: string | null | undefined, locale = "en-GB"): string => {
  if (!iso) return "—";
  const fmt = (FMT_CACHE[locale] ??= new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }));
  return fmt.format(new Date(iso));
};

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
