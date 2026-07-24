import type { SectionCounts } from "../api/types.local";

export type Tone = "ok" | "warn" | "bad" | "failed" | "empty";

/**
 * PS10: no data or non-missing sum = 0 → empty; any failed → failed;
 * else ok/total share: ≥0.95 → ok, ≥0.6 → warn, else bad.
 */
export function sectionTone(stats: SectionCounts | undefined | null): Tone {
  if (!stats) return "empty";
  const total = (stats.ok ?? 0) + (stats.partial ?? 0) + (stats.failed ?? 0) + (stats.skipped ?? 0);
  if (total === 0) return "empty";
  if (stats.failed) return "failed";
  const pct = (stats.ok ?? 0) / total;
  if (pct >= 0.95) return "ok";
  if (pct >= 0.6) return "warn";
  return "bad";
}
