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
    <div className="overflow-hidden rounded border border-gray-200">
      <div className="grid grid-cols-12 gap-2 border-b border-gray-200 bg-gray-100 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
        <div className="col-span-2">{t("ir.code")}</div>
        <div className="col-span-10">{t("ir.description")}</div>
      </div>
      {section.status_codes.map((sc, i) => (
        <div
          key={`${i}-${sc.code}`}
          className="grid grid-cols-12 gap-2 border-b border-gray-100 bg-white px-3 py-1.5 font-mono text-[11px] last:border-0"
        >
          <div className="col-span-2 text-gray-800">{sc.code}</div>
          <div className="col-span-10 truncate text-gray-400" title={sc.description}>
            {sc.description || "—"}
          </div>
        </div>
      ))}
    </div>
  );
}
