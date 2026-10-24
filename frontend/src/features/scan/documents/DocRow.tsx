import { useState } from "react";
import { ODSCollapseDown, ODSNavigationExternalLink, ODSNavigationRight } from "@telekom-ods/react-icons";
import { useDocumentDetail } from "../api/queries";
import type { DocumentListItem } from "../../../shared/api/types";
import { DOC_STATUS_CLS, methodCls } from "../styles";
import { BlockLoadFailed, BlockLoading } from "../components/ServicePageStates";
import { DocSectionRow } from "./DocSectionRow";
import { useI18n } from "../../../shared/i18n";

/**
 * Collapsed row + lazy drill-down (PS12/PS13). Detail is fetched on first
 * expansion (enabled: open) and cached; loading/error/retry come from the
 * query. A 404 on a cached id (snapshot changed underneath) lands in the
 * same error state — retry refetches.
 */
export function DocRow({ serviceName, doc }: { serviceName: string; doc: DocumentListItem }) {
  const [open, setOpen] = useState(false);
  const detail = useDocumentDetail(serviceName, doc.id, open);
  const { t } = useI18n();

  return (
    <div className="border-b border-neutral-100 last:border-0">
      <div
        className="grid cursor-pointer grid-cols-12 items-center gap-3 px-4 py-2 transition hover:bg-neutral-50"
        onClick={() => setOpen(!open)}
      >
        <div className="col-span-1 flex items-center gap-1">
          {open ? <ODSCollapseDown decorative size={13} className="shrink-0 text-neutral-600" /> : <ODSNavigationRight decorative size={13} className="shrink-0 text-neutral-600" />}
          {doc.method ? (
            <span className={`inline-block rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold ${methodCls(doc.method)}`}>
              {doc.method}
            </span>
          ) : (
            <span className="text-xs text-neutral-400">—</span>
          )}
        </div>
        <div className="col-span-4 min-w-0">
          <div className="truncate text-xs font-medium text-ink" title={doc.title ?? undefined}>
            {doc.title || "—"}
          </div>
          <div className="truncate font-mono text-[10px] text-neutral-600" title={doc.path}>
            {doc.path}
          </div>
        </div>
        <div className="col-span-3 truncate font-mono text-xs text-neutral-600" title={doc.uri ?? undefined}>
          {doc.uri || "—"}
        </div>
        <div className="col-span-1">
          <span className={`text-xs font-medium ${DOC_STATUS_CLS[doc.overall_status]}`}>{doc.overall_status}</span>
        </div>
        <div className="col-span-3 flex flex-wrap justify-end gap-1">
          {doc.issues.map((iss) => (
            <span
              key={iss.code}
              className="rounded bg-neutral-50 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-neutral-700 ring-1 ring-neutral-200"
            >
              {iss.code}
              {iss.count > 1 ? ` ×${iss.count}` : ""}
            </span>
          ))}
        </div>
      </div>

      {open && (
        <div className="border-t border-neutral-100 bg-neutral-50 px-10 py-3">
          {detail.isPending ? (
            <BlockLoading label={t("doc.loadingDetail")} />
          ) : detail.isError ? (
            <BlockLoadFailed label={t("doc.detailFailed")} onRetry={() => void detail.refetch()} />
          ) : (
            <>
              <div className="mb-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-neutral-700">
                <span>
                  {detail.data.method} <span className="text-ink-recessive">{detail.data.uri || "—"}</span>
                </span>
                {detail.data.api_version && (
                  <span>
                    {t("doc.apiVersion")} <span className="text-ink-recessive">{detail.data.api_version}</span>
                  </span>
                )}
                {detail.data.failure_reason && (
                  <span className="text-danger">{t("doc.gatingFailure", { reason: detail.data.failure_reason })}</span>
                )}
                <a
                  href={detail.data.source_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="ml-auto flex items-center gap-1 text-neutral-700 transition hover:text-ink"
                  title={t("doc.openSourceHint")}
                >
                  <ODSNavigationExternalLink decorative size={12} /> {t("doc.openSource")}
                </a>
              </div>
              {detail.data.sections.length > 0 ? (
                <div className="grid grid-cols-1 gap-1.5">
                  {detail.data.sections.map((sec) => (
                    <DocSectionRow key={sec.name} section={sec} />
                  ))}
                </div>
              ) : (
                <div className="text-xs text-neutral-600">
                  {detail.data.failure_reason ? t("doc.noSectionsGating") : t("doc.noSections")}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
