import type { SectionCounts } from "../api/types.local";

export type Tone = "ok" | "warn" | "bad" | "failed" | "empty";

/**
 * The worst status present wins: any failed → failed, any partial → warn,
 * otherwise ok. A share threshold would paint "95% fine" as fine, and the one
 * document that is not fine would disappear — the strip answers "is anything
 * wrong in this section", the tooltip carries the scale.
 *
 * `missing` is not a defect: the section is simply absent from those documents,
 * so it neither colours the square nor counts towards a share. A section that
 * is only ever missing has no data to show and renders empty.
 */
export function sectionTone(stats: SectionCounts | undefined | null): Tone {
  if (!stats) return "empty";
  const present = (stats.ok ?? 0) + (stats.partial ?? 0) + (stats.failed ?? 0) + (stats.skipped ?? 0);
  if (present === 0) return "empty";
  if (stats.failed) return "failed";
  if (stats.partial) return "warn";
  if (stats.ok) return "ok";
  return "bad"; // only skipped: extracted from nothing, so nothing is proven
}

const SUMMARY_ORDER = ["failed", "partial", "ok", "skipped", "missing"] as const;

/**
 * "failed 2 · partial 9 · ok 16 · missing 33" — the scale behind the colour,
 * worst first. Zero counters are left out; nothing at all reads as "no data".
 */
export function sectionCountsSummary(stats: SectionCounts | undefined | null): string {
  if (!stats) return "no data";
  const parts = SUMMARY_ORDER.filter((k) => stats[k]).map((k) => `${k} ${stats[k]}`);
  return parts.length ? parts.join(" · ") : "no data";
}
