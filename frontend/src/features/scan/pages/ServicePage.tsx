import { useState } from "react";
import { AlertTriangle, ArrowLeft, Ban, CheckCircle2, FolderOpen, Loader2, RefreshCw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router";
import { ApiError } from "../api/client";
import { useActivateGeneration, useExclude, useRescan } from "../api/mutations";
import { useService, useSummary } from "../api/queries";
import { GenerationBanner } from "../components/GenerationBanner";
import { GenerationSelector } from "../components/GenerationSelector";
import { RescanButton } from "../components/RescanButton";
import { SectionCard } from "../components/SectionCard";
import { StatusPill } from "../components/StatusPill";
import { OverallBar } from "../components/OverallBar";
import { SECTIONS } from "../constants";
import { DocumentsBlock } from "../documents/DocumentsBlock";
import { ExcludeModal } from "../excluded/ExcludeModal";
import { DOC_STATUS_CLS, structOkCls } from "../styles";
import type { DocStatus } from "../api/types.local";
import { useI18n, type MessageKey } from "../../../shared/i18n";

const OVERALL_ORDER: DocStatus[] = ["ok", "partial", "failed", "unsupported"];

/** Service page (PS11 + G1): header with generation selector, metrics, terminal states, documents, admin zone. */
export function ServicePage() {
  const { name = "" } = useParams();
  const navigate = useNavigate();
  const [showExclude, setShowExclude] = useState(false);
  const { t } = useI18n();

  const { data: service, isPending, isError, error, refetch } = useService(name);
  const { data: summary } = useSummary();
  const rescan = useRescan(name);
  const activate = useActivateGeneration(name);
  const exclude = useExclude(name);

  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-gray-400">
        <Loader2 size={16} className="animate-spin" /> {t("service.loading")}
      </div>
    );
  }
  if (isError || !service) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="mx-auto max-w-6xl px-6 py-5">
        <Link to="/scan" className="mb-3 flex items-center gap-1.5 text-sm text-gray-500 transition hover:text-gray-900">
          <ArrowLeft size={15} /> {t("service.back")}
        </Link>
        <div className="rounded-xl border border-gray-200 bg-white p-10 text-center">
          <AlertTriangle size={22} className="mx-auto mb-2 text-gray-400" />
          <div className="mb-1 text-sm font-semibold text-gray-700">
            {notFound ? t("service.notFound", { name }) : t("service.loadFailed")}
          </div>
          {notFound ? (
            <div className="text-xs text-gray-500">{t("service.notFoundHint")}</div>
          ) : (
            <button
              onClick={() => void refetch()}
              className="mx-auto mt-2 flex items-center gap-1 rounded border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500"
            >
              <RefreshCw size={11} /> {t("service.retry")}
            </button>
          )}
        </div>
      </div>
    );
  }
  const scanning = service.scan_status === "scanning";
  const switching = activate.isPending;
  const scannerVersion = summary?.scanner_version ?? "";

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <Link to="/scan" className="mb-3 flex items-center gap-1.5 text-sm text-gray-500 transition hover:text-gray-900">
        <ArrowLeft size={15} /> {t("service.back")}
      </Link>

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="font-mono text-xl font-semibold text-gray-900">{service.name}</h1>
            <StatusPill kind={service.scan_status} by={service.initiated_by ?? undefined} />
          </div>
          {/* G1: replaces the static "scanned with …" line; RollbackButton is gone — the selector covers it */}
          <GenerationSelector
            service={service}
            disabled={scanning || switching}
            onActivate={(id) => activate.mutate(id)}
          />
        </div>
        <div className="flex items-center gap-2">
          {scanning ? (
            <RescanButton reason={null} scanning={{ jobId: service.job_id, startedBy: service.initiated_by ?? undefined }} scannerVersion={scannerVersion} onClick={() => {}} />
          ) : service.rescan_reason ? (
            <RescanButton
              reason={service.rescan_reason}
              scannerVersion={scannerVersion}
              onClick={() => {
                if (!rescan.isPending) rescan.mutate();
              }}
              size="lg"
            />
          ) : (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <CheckCircle2 size={15} className="text-emerald-500" /> {t("service.upToDate")}
              <button
                onClick={() => {
                  if (!rescan.isPending) rescan.mutate();
                }}
                className="text-xs underline decoration-dotted underline-offset-2 transition hover:text-gray-700"
              >
                {t("service.forceRescan")}
              </button>
            </div>
          )}
        </div>
      </div>

      {scanning && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5 text-xs text-blue-800">
          <Loader2 size={14} className="animate-spin" />
          {t("service.scanningBanner", {
            job: service.job_id ? `#${service.job_id}` : "",
            by: service.initiated_by ? t("service.scanningBy", { by: service.initiated_by }) : "",
            at: service.started_at ? t("service.scanningAt", { at: service.started_at }) : "",
          })}
        </div>
      )}

      {!scanning && (
        <GenerationBanner
          service={service}
          onActivateLatest={() => service.latest_generation && activate.mutate(service.latest_generation.id)}
        />
      )}

      {service.error != null || service.interruption != null ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <AlertTriangle size={22} className="mx-auto mb-2 text-red-500" />
          <div className="mb-1 text-sm font-semibold text-red-800">
            {service.interruption ? t(`interruption.${service.interruption.kind}` as MessageKey) : t("service.failedTitle")}
          </div>
          <div className="font-mono text-xs text-red-600">{service.interruption?.message ?? service.error}</div>
          {service.interruption?.kind === "rate_limit" && service.interruption.reset_time != null && (
            <div className="mt-1 font-mono text-xs text-red-500">
              {t("service.rateLimitReset", { time: new Date(service.interruption.reset_time * 1000).toLocaleTimeString() })}
            </div>
          )}
          <div className="mt-2 text-xs text-gray-500">{t("service.failedHint")}</div>
        </div>
      ) : service.documents === 0 && !scanning ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-center">
          <FolderOpen size={22} className="mx-auto mb-2 text-gray-400" />
          <div className="mb-1 text-sm font-semibold text-gray-700">{t("service.noEndpointTitle")}</div>
          <div className="mx-auto max-w-md text-xs text-gray-500">
            {t("service.noEndpointBody", {
              pages: service.non_endpoint_documents
                ? t("service.noEndpointPages", { n: service.non_endpoint_documents })
                : "",
            })}
          </div>
        </div>
      ) : (
        /* G1: while an activation is in flight everything below refetches — shimmer, no interaction */
        <div className={switching ? "pointer-events-none animate-pulse opacity-40" : ""}>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-lg border border-gray-200 bg-white p-3.5">
              <div className="text-xs text-gray-500">{t("service.metricDocs")}</div>
              <div className="mt-0.5 font-mono text-2xl font-semibold tabular-nums text-gray-900">{service.documents}</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3.5">
              <div className="text-xs text-gray-500">{t("service.metricQuality")}</div>
              <div className={`mt-0.5 font-mono text-2xl font-semibold tabular-nums ${structOkCls(service.struct_ok)}`}>
                {service.struct_ok == null ? "—" : `${service.struct_ok}%`}
              </div>
            </div>
            <div className="col-span-2 rounded-lg border border-gray-200 bg-white p-3.5">
              <div className="mb-1.5 text-xs text-gray-500">{t("service.metricStatuses")}</div>
              <OverallBar overall={service.overall_breakdown} docs={service.documents} />
              <div className="mt-1.5 flex flex-wrap gap-x-3 font-mono text-xs tabular-nums">
                {OVERALL_ORDER.map((k) =>
                  service.overall_breakdown[k] ? (
                    <span key={k} className={DOC_STATUS_CLS[k]}>
                      {k} {service.overall_breakdown[k]}
                    </span>
                  ) : null,
                )}
              </div>
            </div>
          </div>

          <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-3">
            {SECTIONS.map((s) => (
              <SectionCard key={s} name={s} stats={service.section_rollup[s]} />
            ))}
          </div>

          {service.top_issues.length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
              <span className="font-semibold uppercase tracking-wide text-gray-500">{t("service.topIssues")}</span>
              {service.top_issues.map((i) => (
                <span key={i.code} className="rounded bg-white px-2 py-1 font-mono tabular-nums text-gray-600 ring-1 ring-gray-200">
                  {i.code} ×{i.count}
                </span>
              ))}
            </div>
          )}

          <DocumentsBlock serviceName={service.name} />
        </div>
      )}

      <div className="mt-10 flex items-center justify-between border-t border-gray-100 pt-3">
        <span className="text-[11px] uppercase tracking-wide text-gray-300">{t("service.admin")}</span>
        <button
          onClick={() => setShowExclude(true)}
          disabled={scanning}
          title={scanning ? t("service.notWhileScanning") : undefined}
          className={`flex items-center gap-1.5 text-xs transition ${
            scanning ? "cursor-not-allowed text-gray-300" : "text-gray-400 hover:text-red-600"
          }`}
        >
          <Ban size={12} /> {t("service.exclude")}
        </button>
      </div>
      {showExclude && (
        <ExcludeModal
          service={service}
          onClose={() => setShowExclude(false)}
          onConfirm={(reason) => {
            setShowExclude(false);
            exclude.mutate(reason, { onSuccess: () => navigate("/scan") });
          }}
        />
      )}
    </div>
  );
}
