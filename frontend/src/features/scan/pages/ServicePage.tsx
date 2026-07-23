import { useState } from "react";
import { AlertTriangle, ArrowLeft, Ban, CheckCircle2, FolderOpen, Loader2, RefreshCw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router";
import { ApiError } from "../api/client";
import { useExclude, useRescan, useRollback } from "../api/mutations";
import { useService, useSummary } from "../api/queries";
import { RescanButton } from "../components/RescanButton";
import { RollbackButton } from "../components/RollbackButton";
import { SectionCard } from "../components/SectionCard";
import { StatusPill } from "../components/StatusPill";
import { OverallBar } from "../components/OverallBar";
import { SECTIONS } from "../constants";
import { DocumentsBlock } from "../documents/DocumentsBlock";
import { ExcludeModal } from "../excluded/ExcludeModal";
import { DOC_STATUS_CLS, structOkCls } from "../styles";
import type { DocStatus } from "../api/types.local";

const OVERALL_ORDER: DocStatus[] = ["ok", "partial", "failed", "unsupported"];

/** Service page (PS11): header, metrics, terminal states, documents, admin zone. */
export function ServicePage() {
  const { name = "" } = useParams();
  const navigate = useNavigate();
  const [showExclude, setShowExclude] = useState(false);

  const { data: service, isPending, isError, error, refetch } = useService(name);
  const { data: summary } = useSummary();
  const rescan = useRescan(name);
  const rollback = useRollback(name);
  const exclude = useExclude(name);

  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-gray-400">
        <Loader2 size={16} className="animate-spin" /> Loading service…
      </div>
    );
  }
  if (isError || !service) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="mx-auto max-w-6xl px-6 py-5">
        <Link to="/scan" className="mb-3 flex items-center gap-1.5 text-sm text-gray-500 transition hover:text-gray-900">
          <ArrowLeft size={15} /> All services
        </Link>
        <div className="rounded-xl border border-gray-200 bg-white p-10 text-center">
          <AlertTriangle size={22} className="mx-auto mb-2 text-gray-400" />
          <div className="mb-1 text-sm font-semibold text-gray-700">
            {notFound ? `Service “${name}” is not in the registry` : "Failed to load service"}
          </div>
          {notFound ? (
            <div className="text-xs text-gray-500">It may have been excluded or renamed.</div>
          ) : (
            <button
              onClick={() => void refetch()}
              className="mx-auto mt-2 flex items-center gap-1 rounded border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500"
            >
              <RefreshCw size={11} /> Retry
            </button>
          )}
        </div>
      </div>
    );
  }
  const scanning = service.scan_status === "scanning";
  const scannerVersion = summary?.scanner_version ?? "";

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <Link to="/scan" className="mb-3 flex items-center gap-1.5 text-sm text-gray-500 transition hover:text-gray-900">
        <ArrowLeft size={15} /> All services
      </Link>

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="font-mono text-xl font-semibold text-gray-900">{service.name}</h1>
            <StatusPill kind={service.scan_status} by={service.started_by} />
          </div>
          <div className="mt-1 font-mono text-xs text-gray-400">
            scanned with v{service.scanner_version ?? scannerVersion}
            {service.scanned_at ? ` · ${service.scanned_at}` : ""} · docs @ main
            {service.docs_changed && <span className="text-amber-600"> · repo HEAD moved since scan</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {scanning ? (
            <RescanButton reason={null} scanning={{ jobId: service.job_id, startedBy: service.started_by }} scannerVersion={scannerVersion} onClick={() => {}} />
          ) : service.rescan_reason ? (
            <RescanButton reason={service.rescan_reason} scannerVersion={scannerVersion} onClick={() => rescan.mutate()} size="lg" />
          ) : (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <CheckCircle2 size={15} className="text-emerald-500" /> Up to date
              <button
                onClick={() => rescan.mutate()}
                className="text-xs underline decoration-dotted underline-offset-2 transition hover:text-gray-700"
              >
                force rescan
              </button>
            </div>
          )}
          <RollbackButton service={service} onRollback={() => rollback.mutate()} />
        </div>
      </div>

      {scanning && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5 text-xs text-blue-800">
          <Loader2 size={14} className="animate-spin" />
          Scan job {service.job_id ? `#${service.job_id} ` : ""}is running
          {service.started_by ? ` — started by ${service.started_by}` : ""}
          {service.started_at ? ` at ${service.started_at}` : ""}. Results below are from the previous scan; the page
          will refresh when the job finishes.
        </div>
      )}

      {service.error != null ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <AlertTriangle size={22} className="mx-auto mb-2 text-red-500" />
          <div className="mb-1 text-sm font-semibold text-red-800">Scan attempted and failed</div>
          <div className="font-mono text-xs text-red-600">{service.error}</div>
          <div className="mt-2 text-xs text-gray-500">No data is stored for this service yet. Retry will queue a new scan job.</div>
        </div>
      ) : service.documents === 0 && !scanning ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-center">
          <FolderOpen size={22} className="mx-auto mb-2 text-gray-400" />
          <div className="mb-1 text-sm font-semibold text-gray-700">Scanned — no endpoint documents found</div>
          <div className="mx-auto max-w-md text-xs text-gray-500">
            api-ref/source exists in this repository
            {service.non_endpoint_documents ? ` and contains ${service.non_endpoint_documents} page(s)` : ""}, but none
            of them is a parseable endpoint document (index and conceptual pages only). Nothing to generate from — this
            is a valid final state, not an error.
          </div>
        </div>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-lg border border-gray-200 bg-white p-3.5">
              <div className="text-xs text-gray-500">Endpoint documents</div>
              <div className="mt-0.5 font-mono text-2xl font-semibold tabular-nums text-gray-900">{service.documents}</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3.5">
              <div className="text-xs text-gray-500">Structural quality</div>
              <div className={`mt-0.5 font-mono text-2xl font-semibold tabular-nums ${structOkCls(service.struct_ok)}`}>
                {service.struct_ok == null ? "—" : `${service.struct_ok}%`}
              </div>
            </div>
            <div className="col-span-2 rounded-lg border border-gray-200 bg-white p-3.5">
              <div className="mb-1.5 text-xs text-gray-500">Document statuses</div>
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
              <span className="font-semibold uppercase tracking-wide text-gray-500">Top issues:</span>
              {service.top_issues.map((i) => (
                <span key={i.code} className="rounded bg-white px-2 py-1 font-mono tabular-nums text-gray-600 ring-1 ring-gray-200">
                  {i.code} ×{i.count}
                </span>
              ))}
            </div>
          )}

          <DocumentsBlock serviceName={service.name} />
        </>
      )}

      <div className="mt-10 flex items-center justify-between border-t border-gray-100 pt-3">
        <span className="text-[11px] uppercase tracking-wide text-gray-300">Administrative</span>
        <button
          onClick={() => setShowExclude(true)}
          disabled={scanning}
          title={scanning ? "Not available while a scan job is running" : undefined}
          className={`flex items-center gap-1.5 text-xs transition ${
            scanning ? "cursor-not-allowed text-gray-300" : "text-gray-400 hover:text-red-600"
          }`}
        >
          <Ban size={12} /> Exclude from registry…
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
