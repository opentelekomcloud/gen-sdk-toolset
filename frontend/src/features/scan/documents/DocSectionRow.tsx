import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { SectionDetail } from "../api/types.local";
import { SECTION_LABELS } from "../constants";
import { SECTION_STATUS_CLS } from "../styles";
import { IrTable } from "./IrTable";

export function DocSectionRow({ section }: { section: SectionDetail }) {
  const [open, setOpen] = useState(false);
  const counts =
    section.fields_total > 0
      ? ` · ${section.fields_recognized}/${section.fields_total} fields${
          section.fields_unknown_type ? ` · ${section.fields_unknown_type} unknown` : ""
        }`
      : "";
  return (
    <div className="rounded border border-gray-200 bg-white">
      <div
        className="flex cursor-pointer items-center justify-between px-2.5 py-1.5 hover:bg-gray-50"
        onClick={() => setOpen(!open)}
      >
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
          {open ? <ChevronDown size={12} className="text-gray-400" /> : <ChevronRight size={12} className="text-gray-400" />}
          {SECTION_LABELS[section.name]}
        </span>
        <span className={`font-mono text-[11px] font-medium ${SECTION_STATUS_CLS[section.status]}`}>
          {section.status}
          {counts}
        </span>
      </div>
      {section.issues.map((i, idx) => (
        <div
          key={idx}
          className="truncate px-2.5 pb-1 font-mono text-[10px] text-gray-500"
          title={`${i.code} ${i.location ?? ""} ${i.details ?? ""}`}
        >
          <span className="text-amber-700">{i.code}</span>
          {i.location ? ` @ ${i.location}` : ""}
          {i.details ? ` — ${i.details}` : ""}
        </div>
      ))}
      {open && (
        <div className="border-t border-gray-100 p-2">
          <IrTable section={section} />
        </div>
      )}
    </div>
  );
}
