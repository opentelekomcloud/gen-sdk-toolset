import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, FileText, Search } from "lucide-react";
import { useDocuments } from "../api/queries";
import type { DocStatus } from "../api/types.local";
import { chipCls } from "../styles";
import { DocRow } from "./DocRow";
import { useI18n, type MessageKey } from "../../../shared/i18n";

const CHIP_ORDER: (DocStatus | "all")[] = ["all", "failed", "unsupported", "partial", "ok"];

/** Documents block on the service page (PS12): server-side filter/search/pagination. */
export function DocumentsBlock({ serviceName }: { serviceName: string }) {
  const [status, setStatus] = useState<DocStatus | "all">("all");
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [page, setPage] = useState(1);
  const { t } = useI18n();

  /* Debounce keystrokes so each letter doesn't fire an API request. */
  useEffect(() => {
    const timer = setTimeout(() => setQDebounced(q), 300);
    return () => clearTimeout(timer);
  }, [q]);

  const { data } = useDocuments(serviceName, { status, q: qDebounced, page });
  if (!data) return null;

  const chips = CHIP_ORDER.filter((k) => k === "all" || data.doc_counts[k]);
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
  const from = (data.page - 1) * data.page_size + 1;
  const to = Math.min(data.page * data.page_size, data.total);

  return (
    <>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <FileText size={15} className="text-gray-400" />
        <span className="text-sm font-semibold text-gray-700">{t("docs.title")}</span>
        {chips.map((k) => (
          <button
            key={k}
            onClick={() => {
              setStatus(k);
              setPage(1);
            }}
            className={chipCls(status === k)}
          >
            {t(`docstatus.${k}` as MessageKey)} <span className="font-mono tabular-nums opacity-70">{data.doc_counts[k] ?? 0}</span>
          </button>
        ))}
        <div className="relative ml-auto">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder={t("docs.filter")}
            className="w-48 rounded-md border border-gray-300 bg-white py-1 pl-7 pr-2 text-xs outline-none transition focus:border-gray-500"
          />
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {data.items.map((doc) => (
          <DocRow key={doc.id} serviceName={serviceName} doc={doc} />
        ))}
        {data.items.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-gray-400">{t("docs.empty")}</div>
        )}
      </div>

      {data.total > 0 && (
        <div className="mt-2 flex items-center justify-between text-xs text-gray-400">
          <span>{t("docs.showing", { from, to, total: data.total })}</span>
          <span className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={data.page <= 1}
              className={`flex items-center gap-0.5 rounded border px-2 py-1 transition ${
                data.page <= 1 ? "cursor-not-allowed border-gray-200 text-gray-300" : "border-gray-300 text-gray-600 hover:border-gray-500"
              }`}
            >
              <ChevronLeft size={12} /> {t("docs.prev")}
            </button>
            <span className="px-2 font-mono tabular-nums">{t("docs.page", { p: data.page, total: totalPages })}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={data.page >= totalPages}
              className={`flex items-center gap-0.5 rounded border px-2 py-1 transition ${
                data.page >= totalPages
                  ? "cursor-not-allowed border-gray-200 text-gray-300"
                  : "border-gray-300 text-gray-600 hover:border-gray-500"
              }`}
            >
              {t("docs.next")} <ChevronRight size={12} />
            </button>
          </span>
        </div>
      )}
    </>
  );
}
