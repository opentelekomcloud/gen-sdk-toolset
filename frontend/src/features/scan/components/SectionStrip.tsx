import type { Section, SectionCounts } from "../api/types.local";
import { SECTIONS, sectionLabelKey } from "../constants";
import { sectionTone } from "../lib/sectionTone";
import { TONE_BG } from "../styles";
import { useI18n } from "../../../shared/i18n";

/** 7 squares in fixed order; a missing section renders muted without breaking the strip. */
export function SectionStrip({ sections }: { sections: Record<Section, SectionCounts> | null }) {
  const { t } = useI18n();
  if (!sections) return <span className="text-xs text-gray-300">·······</span>;
  return (
    <div className="flex gap-0.5">
      {SECTIONS.map((s) => {
        const tone = sectionTone(sections[s]);
        return (
          <div
            key={s}
            title={t(sectionLabelKey(s))}
            className={`h-3.5 w-3.5 rounded-sm ${TONE_BG[tone]} ${tone === "empty" ? "opacity-60" : ""}`}
          />
        );
      })}
    </div>
  );
}
