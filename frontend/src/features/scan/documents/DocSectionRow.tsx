import { useState } from "react";
import { ODSCollapseDown, ODSNavigationRight } from "@telekom-ods/react-icons";
import type { SectionDetail } from "../../../shared/api/types";
import { sectionLabelKey } from "../constants";
import { SECTION_STATUS_CLS } from "../styles";
import { IrTable } from "./IrTable";
import { StatusCodeTable } from "./StatusCodeTable";
import { useI18n } from "../../../shared/i18n";

export function DocSectionRow({ section }: { section: SectionDetail }) {
  const [open, setOpen] = useState(false);
  const { t } = useI18n();
  const counts =
    section.fields_total > 0
      ? ` · ${t("doc.fields", { rec: section.fields_recognized, total: section.fields_total })}${
          section.fields_unknown_type ? ` · ${t("doc.unknown", { n: section.fields_unknown_type })}` : ""
        }`
      : "";
  return (
    <div className="rounded border border-neutral-200 bg-surface">
      <div
        className="flex cursor-pointer items-center justify-between px-2.5 py-1.5 hover:bg-neutral-50"
        onClick={() => setOpen(!open)}
      >
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-neutral-700">
          {open ? <ODSCollapseDown decorative size={12} className="text-neutral-600" /> : <ODSNavigationRight decorative size={12} className="text-neutral-600" />}
          {t(sectionLabelKey(section.name))}
        </span>
        <span className={`font-mono text-[11px] font-medium ${SECTION_STATUS_CLS[section.status]}`}>
          {section.status}
          {counts}
        </span>
      </div>
      {section.issues.map((i, idx) => (
        <div
          key={idx}
          className="truncate px-2.5 pb-1 font-mono text-[10px] text-neutral-700"
          title={`${i.code} ${i.location ?? ""} ${i.details ?? ""}`}
        >
          <span className="text-warning">{i.code}</span>
          {i.location ? ` @ ${i.location}` : ""}
          {i.details ? ` — ${i.details}` : ""}
        </div>
      ))}
      {open && (
        <div className="space-y-2 border-t border-neutral-100 p-2">
          {/* `?? []` guards a detail cached before examples existed: the query
              keeps document details forever (staleTime: Infinity). */}
          {(section.examples ?? []).map((example, idx) => (
            <figure key={idx} className="overflow-hidden rounded border border-neutral-200">
              <figcaption className="flex items-center justify-between gap-2 border-b border-neutral-200 bg-surface px-2 py-1 text-[10px] text-neutral-700">
                <span className="truncate">{example.label || t("doc.example")}</span>
                {example.language && <span className="font-mono">{example.language}</span>}
              </figcaption>
              <pre className="max-h-72 overflow-auto bg-neutral-900 px-3 py-2 text-[11px] leading-relaxed text-neutral-100">
                <code>{example.raw}</code>
              </pre>
            </figure>
          ))}
          {/* Status codes are neither parameters nor examples, so they get
              their own table rather than being folded into either. `?? []`
              guards a detail cached before they existed: the query keeps
              document details forever (staleTime: Infinity). */}
          {(section.status_codes ?? []).length > 0 && <StatusCodeTable section={section} />}
          {(section.examples ?? []).length === 0 &&
            (section.status_codes ?? []).length === 0 && <IrTable section={section} />}
        </div>
      )}
    </div>
  );
}
