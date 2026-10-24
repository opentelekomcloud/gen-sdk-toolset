import { useState } from "react";
import type { DocFilter, DocStatus, RepositoryInterruption } from "../types";
import { ODSDownload, ODSFolder, ODSStatusInactive, ODSSuccess, ODSWarning } from "@telekom-ods/react-icons";
import { Spinner } from "../../../shared/ui/Spinner";
import { ODSButton } from "@telekom-ods/react-ui-kit/ODSButton";
import { ODSInlineNotification } from "@telekom-ods/react-ui-kit/ODSInlineNotification";
import { ODSLink } from "@telekom-ods/react-ui-kit/ODSLink";
import { useNavigate, useParams } from "react-router";
import { ApiError } from "../api/client";
import { useActivateSnapshot, useExclude, useRescan } from "../api/mutations";
import { useService, useSummary } from "../api/queries";
import { SnapshotBanner } from "../components/SnapshotBanner";
import { SnapshotSelector } from "../components/SnapshotSelector";
import { RescanButton } from "../components/RescanButton";
import { ScanJobWatcher } from "../components/ScanJobWatcher";
import { SectionCard } from "../components/SectionCard";
import { RefusalBanner, ServiceBackLink, ServiceLoadFailed, ServiceLoading } from "../components/ServicePageStates";
import { StatusPill } from "../components/StatusPill";
import { OverallBar } from "../components/OverallBar";
import { SECTIONS } from "../constants";
import { DocumentsBlock } from "../documents/DocumentsBlock";
import { ExcludeModal } from "../excluded/ExcludeModal";
import { useSession } from "../../../shared/auth/useSession";
import { activationErrorKey, mutationErrorKey } from "../lib/errors";
import { fmtSnapshotAt } from "../lib/snapshot";
import { DOC_STATUS_CLS, structOkCls } from "../styles";
import { useI18n, type MessageKey } from "../../../shared/i18n";

const OVERALL_ORDER: DocStatus[] = ["ok", "partial", "failed", "unsupported"];

interface Refusable {
  isError: boolean;
  error: Error | null;
  reset: () => void;
}

/** What to say about a mutation that was refused, or nothing if it was not. */
function refusalOf(mutation: Refusable, key: (error: unknown) => MessageKey) {
  if (!mutation.isError || !mutation.error) return null;
  return { key: key(mutation.error), error: mutation.error, dismiss: () => mutation.reset() };
}

/** Service page (PS11 + G1): header with snapshot selector, metrics, terminal states, documents, admin zone. */
export function ServicePage() {
  const { name = "" } = useParams();
  const navigate = useNavigate();
  const [showExclude, setShowExclude] = useState(false);
  /* What the documents below are narrowed to: a section count or an issue code. */
  const [filter, setFilter] = useState<DocFilter | null>(null);
  const { canWrite } = useSession();
  const { t } = useI18n();

  const { data: service, isPending, isError, error, refetch } = useService(name);
  const { data: summary } = useSummary();
  const rescan = useRescan(name);
  const activate = useActivateSnapshot(name);
  const exclude = useExclude(name);

  if (isPending) return <ServiceLoading />;
  if (isError || !service) {
    const notFound = error instanceof ApiError && error.status === 404;
    return <ServiceLoadFailed back="/scan" onRetry={() => void refetch()} notFound={notFound ? name : undefined} />;
  }
  const scanning = service.scan_status === "scanning";
  const switching = activate.isPending;
  const scannerVersion = summary?.scanner_version ?? "";
  /* A JSONB column, so the schema promises only an object of unknown values -
     it overlaps nothing, hence the two-step cast. Ingest writes a
     RepositoryInterruption; this is the one place that says so. */
  const interruption = service.interruption as unknown as RepositoryInterruption | null;
  /* One refusal on screen at a time: activation names its own cases, the other
     two share the generic wording. */
  const refusal =
    refusalOf(activate, activationErrorKey) ??
    refusalOf(rescan, mutationErrorKey) ??
    refusalOf(exclude, mutationErrorKey);
  /* a failed job persists nothing — with an active snapshot the failure is a warning, without one a terminal state */
  const jobFailed = service.error != null || interruption != null;

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <ServiceBackLink to="/scan" />

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="font-mono text-xl font-semibold text-ink">{service.label}</h1>
            <StatusPill kind={service.scan_status} />
          </div>
          {/* G1: replaces the static "scanned with …" line; RollbackButton is gone — the selector covers it */}
          <SnapshotSelector
            /* Readable by everyone, switchable by a worker: the popover still
               opens, so a viewer can see which snapshot is being served. */
            service={service}
            disabled={scanning || switching || !canWrite}
            onActivate={(id) => activate.mutate(id)}
          />
        </div>
        <div className="flex items-center gap-2">
          {!canWrite && !scanning ? null : scanning ? (
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
            <div className="flex items-center gap-2 text-sm text-neutral-600">
              <ODSSuccess decorative size={15} className="text-success" /> {t("service.upToDate")}
              <ODSButton
                size="small"
                variant="ghost"
                label={t("service.forceRescan")}
                onClick={() => {
                  if (!rescan.isPending) rescan.mutate();
                }}
              />
            </div>
          )}
        </div>
      </div>

      {/* A refused mutation changes nothing on screen, so say why it did not
          take. Each of these has already rolled its optimistic state back and
          refetched, so the page around the banner is in step with the server.
          A 403 lands here when the UI offered something this session may not do
          - hiding the control is the courtesy, this is the answer. */}
      {refusal && (
        <RefusalBanner title={t(refusal.key)} message={refusal.error.message} onDismiss={refusal.dismiss} />
      )}

      {scanning && service.job_id != null && (
        <ScanJobWatcher key={service.job_id} serviceName={service.name} jobId={service.job_id} />
      )}

      {scanning && (
        <ODSInlineNotification
          className="mb-4"
          mode="informative"
          informationIcon={<Spinner />}
          showCloseButton={false}
          text={t("service.scanningBanner", {
            job: service.job_id ? `#${service.job_id}` : "",
            by: service.initiated_by ? t("service.scanningBy", { by: service.initiated_by }) : "",
            at: service.started_at ? t("service.scanningAt", { at: service.started_at }) : "",
          })}
        />
      )}

      {!scanning && (
        <SnapshotBanner
          canActivate={canWrite}
          service={service}
          onActivateLatest={() => service.latest_snapshot && activate.mutate(service.latest_snapshot.id)}
        />
      )}

      {!scanning && jobFailed && service.active_snapshot != null && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-danger-line bg-danger-subtle px-4 py-2.5 text-xs text-danger">
          <ODSWarning decorative size={14} className="mt-px shrink-0 text-danger" />
          <div className="min-w-0">
            <span className="font-semibold">
              {interruption ? t(`interruption.${interruption.kind}` as MessageKey) : t("service.failedBannerTitle")}
            </span>
            {" — "}
            <span className="font-mono">{interruption?.message ?? service.error}</span>
            {service.error_at != null && <span className="font-mono text-danger"> · {fmtSnapshotAt(service.error_at)}</span>}
            {interruption?.kind === "rate_limit" && interruption.reset_time != null && (
              <span className="font-mono text-danger">
                {" · "}
                {t("service.rateLimitReset", { time: new Date(interruption.reset_time * 1000).toLocaleTimeString() })}
              </span>
            )}
            <div className="mt-0.5 text-danger/80">
              {t("service.failedKeptData", { gen: service.active_snapshot.id, at: fmtSnapshotAt(service.active_snapshot.last_scanned_at) })}
            </div>
          </div>
          {canWrite && (
            <ODSButton
              className="ml-auto shrink-0"
              size="small"
              variant="outline"
              label={t("service.retry")}
              onClick={() => rescan.mutate()}
            />
          )}
        </div>
      )}

      {jobFailed && service.active_snapshot == null ? (
        <div className="rounded-xl border border-danger-line bg-danger-subtle p-8 text-center">
          <ODSWarning decorative size={24} className="mx-auto mb-2 block text-danger" />
          <div className="mb-1 text-sm font-semibold text-danger">
            {interruption ? t(`interruption.${interruption.kind}` as MessageKey) : t("service.failedTitle")}
          </div>
          <div className="font-mono text-xs text-danger">{interruption?.message ?? service.error}</div>
          {interruption?.kind === "rate_limit" && interruption.reset_time != null && (
            <div className="mt-1 font-mono text-xs text-danger">
              {t("service.rateLimitReset", { time: new Date(interruption.reset_time * 1000).toLocaleTimeString() })}
            </div>
          )}
          <div className="mt-2 text-xs text-neutral-700">{t("service.failedHint")}</div>
        </div>
      ) : service.documents === 0 && !scanning ? (
        <div className="rounded-xl border border-neutral-200 bg-surface p-8 text-center">
          <ODSFolder decorative size={24} className="mx-auto mb-2 block text-neutral-600" />
          <div className="mb-1 text-sm font-semibold text-ink-recessive">{t("service.noEndpointTitle")}</div>
          <div className="mx-auto max-w-md text-xs text-neutral-700">
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
            <div className="rounded-lg border border-neutral-200 bg-surface p-3.5">
              <div className="text-xs text-neutral-700">{t("service.metricDocs")}</div>
              <div className="mt-0.5 font-mono text-2xl font-semibold tabular-nums text-ink">{service.documents}</div>
              <div className="mt-0.5 font-mono text-[11px] tabular-nums text-neutral-600">
                {t("service.readSplit", {
                  read: service.read_in_full ?? 0,
                  rows: service.rows_unrecognized,
                  unread: service.unread_documents,
                })}
              </div>
            </div>
            <div className="rounded-lg border border-neutral-200 bg-surface p-3.5">
              <div className="text-xs text-neutral-700">{t("service.metricQuality")}</div>
              <div
                className={`mt-0.5 font-mono text-2xl font-semibold tabular-nums ${structOkCls(service.docs_ok)}`}
                title={service.unread_documents ? t("registry.docsOkBound", { n: service.unread_documents }) : undefined}
              >
                {service.docs_ok == null ? "—" : `${service.unread_documents ? "≤ " : ""}${service.docs_ok}%`}
              </div>
            </div>
            <div className="col-span-2 rounded-lg border border-neutral-200 bg-surface p-3.5">
              <div className="mb-1.5 text-xs text-neutral-700">{t("service.metricStatuses")}</div>
              <OverallBar overall={service.overall_breakdown} docs={service.documents} unread={service.unread_breakdown} />
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
              <SectionCard
                key={s}
                name={s}
                stats={service.section_rollup[s]}
                active={filter?.kind === "section" && filter.section === s ? filter.status : null}
                onPick={(status) =>
                  setFilter((current) =>
                    current?.kind === "section" && current.section === s && current.status === status
                      ? null
                      : { kind: "section", section: s, status },
                  )
                }
              />
            ))}
          </div>

          {service.active_snapshot && (
            <div className="mb-4">
              <ODSLink
                href={`/api/scan/services/${encodeURIComponent(service.name)}/export`}
                title={t("service.exportHint")}
                label={t("service.export")}
                leftIcon={<ODSDownload decorative small />}
              />
            </div>
          )}

          {service.top_issues.length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
              <span className="font-semibold uppercase tracking-wide text-neutral-700">{t("service.topIssues")}</span>
              {service.top_issues.map((i) => (
                <button
                  key={i.code}
                  type="button"
                  title={t("service.issueFilterHint")}
                  onClick={() =>
                    setFilter((current) =>
                      current?.kind === "issue" && current.code === i.code ? null : { kind: "issue", code: i.code },
                    )
                  }
                  className={`rounded px-2 py-1 font-mono tabular-nums ring-1 transition ${
                    filter?.kind === "issue" && filter.code === i.code
                      ? "bg-contrast text-on-contrast ring-contrast"
                      : "bg-surface text-ink-recessive ring-neutral-200 hover:ring-neutral-500"
                  }`}
                >
                  {i.code} ×{i.count}
                </button>
              ))}
            </div>
          )}

          <DocumentsBlock
            /* A different section filter is a different result set: the key
               remounts the block so paging and search start clean. */
            key={filter ? (filter.kind === "section" ? `${filter.section}-${filter.status}` : filter.code) : "all"}
            serviceName={service.name}
            filter={filter}
            onClearFilter={() => setFilter(null)}
          />
        </div>
      )}

      <div className="mt-10 flex items-center justify-between border-t border-neutral-100 pt-3">
        <span className="text-[11px] uppercase tracking-wide text-neutral-400">{t("service.admin")}</span>
        {canWrite && (
          <ODSButton
            size="small"
            variant="ghost"
            label={t("service.exclude")}
            buttonIcon={<ODSStatusInactive decorative />}
            leftIcon
            onClick={() => setShowExclude(true)}
            disabled={scanning}
            title={scanning ? t("service.notWhileScanning") : undefined}
          />
        )}
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
