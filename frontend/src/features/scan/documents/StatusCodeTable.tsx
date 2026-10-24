import type { SectionDetail } from "../../../shared/api/types";
import { useI18n } from "../../../shared/i18n";

/**
 * The status codes of one section.
 *
 * Its own table rather than a column added to `IrTable`: a status code has no
 * type and no mandatory flag, so it would leave two of that table's four
 * columns empty on every row and invite the reader to wonder what the blanks
 * mean.
 */
export function StatusCodeTable({ section }: { section: SectionDetail }) {
  const { t } = useI18n();
  return (
    <div className="overflow-hidden rounded border border-neutral-200">
      <div className="grid grid-cols-12 gap-2 border-b border-neutral-200 bg-neutral-100 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-neutral-700">
        <div className="col-span-2">{t("ir.code")}</div>
        <div className="col-span-10">{t("ir.description")}</div>
      </div>
      {section.status_codes.map((sc, i) => (
        <div
          key={`${i}-${sc.code}`}
          className="grid grid-cols-12 gap-2 border-b border-neutral-100 bg-surface px-3 py-1.5 font-mono text-[11px] last:border-0"
        >
          <div className="col-span-2 text-ink">{sc.code}</div>
          <div className="col-span-10 truncate text-neutral-600" title={sc.description}>
            {sc.description || "—"}
          </div>
        </div>
      ))}
    </div>
  );
}
