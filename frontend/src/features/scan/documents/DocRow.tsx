import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import { useDocumentDetail } from "../api/queries";
import type { DocumentListItem } from "../api/types.local";
import { DOC_STATUS_CLS, methodCls } from "../styles";
import { DocSectionRow } from "./DocSectionRow";

/**
 * Collapsed row + lazy drill-down (PS12/PS13). Detail is fetched on first
 * expansion (enabled: open) and cached; loading/error/retry come from the
 * query. A 404 on a cached id (generation changed underneath) lands in the
 * same error state — retry refetches.
 */
export function DocRow({ serviceName, doc }: { serviceName: string; doc: DocumentListItem }) {
  const [open, setOpen] = useState(false);
  const detail = useDocumentDetail(serviceName, doc.id, open);

  return (
    <div className="border-b border-gray-100 last:border-0">
      <div
        className="grid cursor-pointer grid-cols-12 items-center gap-3 px-4 py-2 transition hover:bg-gray-50"
        onClick={() => setOpen(!open)}
      >
        <div className="col-span-1 flex items-center gap-1">
          {open ? <ChevronDown size={13} className="shrink-0 text-gray-400" /> : <ChevronRight size={13} className="shrink-0 text-gray-400" />}
          {doc.method ? (
            <span className={`inline-block rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold ${methodCls(doc.method)}`}>
              {doc.method}
            </span>
          ) : (
            <span className="text-xs text-gray-300">—</span>
          )}
        </div>
        <div className="col-span-4 min-w-0">
          <div className="truncate text-xs font-medium text-gray-800" title={doc.title ?? undefined}>
            {doc.title || "—"}
          </div>
          <div className="truncate font-mono text-[10px] text-gray-400" title={doc.document}>
            {doc.document}
          </div>
        </div>
        <div className="col-span-3 truncate font-mono text-xs text-gray-400" title={doc.uri ?? undefined}>
          {doc.uri || "—"}
        </div>
        <div className="col-span-1">
          <span className={`text-xs font-medium ${DOC_STATUS_CLS[doc.overall_status]}`}>{doc.overall_status}</span>
        </div>
        <div className="col-span-3 flex flex-wrap justify-end gap-1">
          {doc.issues.map((iss) => (
            <span
              key={iss.code}
              className="rounded bg-gray-50 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-gray-500 ring-1 ring-gray-200"
            >
              {iss.code}
              {iss.count > 1 ? ` ×${iss.count}` : ""}
            </span>
          ))}
        </div>
      </div>

      {open && (
        <div className="border-t border-gray-100 bg-gray-50 px-10 py-3">
          {detail.isPending ? (
            <div className="flex items-center gap-2 py-3 text-xs text-gray-500">
              <Loader2 size={14} className="animate-spin text-gray-400" /> Loading document detail…
            </div>
          ) : detail.isError ? (
            <div className="flex items-center justify-between rounded border border-red-200 bg-red-50 px-3 py-2">
              <span className="flex items-center gap-2 text-xs text-red-700">
                <AlertTriangle size={13} /> Failed to load document detail
              </span>
              <button
                onClick={() => void detail.refetch()}
                className="flex items-center gap-1 rounded border border-red-300 px-2 py-1 text-xs font-medium text-red-700 transition hover:border-red-500"
              >
                <RefreshCw size={11} /> Retry
              </button>
            </div>
          ) : (
            <>
              <div className="mb-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-gray-500">
                <span>
                  {detail.data.method} <span className="text-gray-700">{detail.data.uri || "—"}</span>
                </span>
                {detail.data.api_version && (
                  <span>
                    api version: <span className="text-gray-700">{detail.data.api_version}</span>
                  </span>
                )}
                {detail.data.failure_reason && (
                  <span className="text-red-600">gating failure: {detail.data.failure_reason}</span>
                )}
              </div>
              {detail.data.sections.length > 0 ? (
                <div className="grid grid-cols-1 gap-1.5">
                  {detail.data.sections.map((sec) => (
                    <DocSectionRow key={sec.name} section={sec} />
                  ))}
                </div>
              ) : (
                <div className="text-xs text-gray-400">
                  {detail.data.failure_reason
                    ? "No sections extracted — gating failed before content parsing."
                    : "No section data."}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
