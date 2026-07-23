import type { Section, SectionCounts, SectionStatus } from "../api/types.local";
import { SECTION_LABELS } from "../constants";
import { sectionTone } from "../lib/sectionTone";
import { SECTION_STATUS_CLS, TONE_BG } from "../styles";

const ORDER: SectionStatus[] = ["ok", "partial", "failed", "skipped", "missing"];

export function SectionCard({ name, stats }: { name: Section; stats: SectionCounts | undefined }) {
  const tone = sectionTone(stats);
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <div className="mb-1.5 flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-sm ${TONE_BG[tone]}`} />
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-600">{SECTION_LABELS[name]}</span>
      </div>
      {stats ? (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-xs tabular-nums">
          {ORDER.filter((k) => stats[k]).map((k) => (
            <span key={k} className={SECTION_STATUS_CLS[k]}>
              {k} {stats[k]}
            </span>
          ))}
        </div>
      ) : (
        <span className="text-xs text-gray-400">no data</span>
      )}
    </div>
  );
}
