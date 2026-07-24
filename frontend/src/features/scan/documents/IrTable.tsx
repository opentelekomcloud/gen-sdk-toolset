import type { Parameter, SectionDetail } from "../api/types.local";
import { Fragment } from "react";
import { useI18n } from "../../../shared/i18n";

function ParamRows({ params, depth = 0 }: { params: Parameter[]; depth?: number }) {
  const { t } = useI18n();
  return (
    <>
      {params.map((p, i) => {
        const unknown = p.param_type === "Unknown";
        return (
          <Fragment key={`${depth}-${i}-${p.name}`}>
            <div
              className={`grid grid-cols-12 gap-2 border-b border-gray-100 px-3 py-1.5 font-mono text-[11px] last:border-0 ${
                unknown ? "bg-amber-50" : "bg-white"
              }`}
            >
              <div className="col-span-3 truncate text-gray-800" style={{ paddingLeft: depth * 14 }} title={p.name}>
                {depth > 0 && <span className="text-gray-300">└ </span>}
                {p.name}
              </div>
              <div
                className={`col-span-3 truncate ${unknown ? "font-semibold text-amber-700" : "text-gray-600"}`}
                title={p.param_type}
              >
                {unknown ? t("ir.unknown") : p.param_type}
              </div>
              <div className="col-span-1 text-gray-500">{p.mandatory ? t("ir.yes") : "—"}</div>
              <div className="col-span-5 truncate text-gray-400" title={p.description}>
                {p.description || "—"}
              </div>
            </div>
            {p.children && <ParamRows params={p.children} depth={depth + 1} />}
          </Fragment>
        );
      })}
    </>
  );
}

/** Parameter table for one section (PS13). Lives in features/scan/documents, not shared. */
export function IrTable({ section }: { section: SectionDetail }) {
  const { t } = useI18n();
  if (!section.parameters) {
    return <div className="px-3 py-2 text-xs text-gray-400">{t("ir.noTable")}</div>;
  }
  return (
    <div className="overflow-hidden rounded border border-gray-200">
      <div className="grid grid-cols-12 gap-2 border-b border-gray-200 bg-gray-100 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
        <div className="col-span-3">{t("ir.field")}</div>
        <div className="col-span-3">{t("ir.type")}</div>
        <div className="col-span-1">{t("ir.req")}</div>
        <div className="col-span-5">{t("ir.description")}</div>
      </div>
      <ParamRows params={section.parameters} />
    </div>
  );
}
