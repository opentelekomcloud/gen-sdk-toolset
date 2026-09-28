import { useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  ExternalLink,
  GitPullRequest,
  Loader2,
  Play,
  RefreshCw,
} from "lucide-react";
import { useLocation, useParams, useSearchParams } from "react-router";
import {
  useGenerationResources,
  useGenerationServices,
  useGenerationSpec,
  useGenerationTargets,
  useOtcSettings,
} from "../data/queries";
import { useLiveCall, useRefreshPullRequest, useStartGeneration } from "../data/mutations";
import type { GenJobStatus, GenLiveResponse, GenOperation, GenState } from "../data/types";
import { HoldReason } from "../components/HoldReason";
import { PageNotFound } from "../components/PageNotFound";
import { holdOf, undecided } from "../lib/layout";
import { listPath, servicePath, type FromSpec } from "../lib/paths";
import { pathParams } from "../lib/uri";
import { GEN_STATE_CLS, genStateKey } from "../styles";
import { StatusPill } from "../../scan/components/StatusPill";
import {
  RefusalBanner,
  ServiceBackLink,
  ServiceLoadFailed,
  ServiceLoading,
} from "../../scan/components/ServicePageStates";
import { mutationErrorKey } from "../../scan/lib/errors";
import { fmtSnapshotAt } from "../../scan/lib/snapshot";
import { methodCls } from "../../scan/styles";
import { useSession } from "../../../shared/auth/useSession";
import { useI18n, type MessageKey } from "../../../shared/i18n";

/** A job's pill is the state a service would be in with that job alone - the prototype's. */
const JOB_STATE: Record<GenJobStatus, GenState> = {
  running: "in_progress",
  done: "review",
  merged: "done",
  failed: "failed",
};

/** Where a live call of an operation stands. */
type CallStatus = "none" | "sending" | "ok" | "failed";

const CALL_CLS: Record<CallStatus, string> = {
  none: "border-gray-200 bg-gray-50 text-gray-400",
  sending: "border-blue-200 bg-blue-50 text-blue-700",
  ok: "border-emerald-200 bg-emerald-50 text-emerald-700",
  failed: "border-red-200 bg-red-50 text-red-700",
};

const INPUT_CLS =
  "min-w-0 flex-1 rounded border border-gray-300 bg-white px-2 py-1 font-mono text-[11px] text-gray-800 outline-none focus:border-gray-500";

/** What was typed for an operation's call: path and query values by parameter name. */
interface Inputs {
  path: Record<string, string>;
  query: Record<string, string>;
}

/** An operation's call: whether one is on its way, and the answer to the last one. */
interface Run {
  sending: boolean;
  response: GenLiveResponse | null;
}

/** A list asks for a page of 20 until told otherwise - the prototype's prefill; everything else starts empty. */
const prefill = (param: string) => (param === "limit" ? "20" : "");

/** The query values a call goes out with: what was typed, or the prefill; an empty one is not sent. */
const queryValues = (op: GenOperation, inputs: Inputs | undefined): Record<string, string> =>
  Object.fromEntries(
    op.query.map((p) => [p.name, inputs?.query[p.name] ?? prefill(p.name)]).filter(([, value]) => value.trim()),
  );

/** A folding group of a call's parameters. */
function ParamGroup({
  label,
  summary,
  open,
  onToggle,
  children,
}: {
  label: string;
  summary: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        {open ? (
          <ChevronDown size={12} className="shrink-0 text-gray-400" />
        ) : (
          <ChevronRight size={12} className="shrink-0 text-gray-400" />
        )}
        <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">{label}</span>
        <span className="truncate font-mono text-[10px] text-gray-400">{summary}</span>
      </button>
      {open && <div className="flex flex-col gap-1.5 border-t border-gray-100 px-3 py-2.5">{children}</div>}
    </div>
  );
}

/** What OTC answered: the status, how long it took, what went wrong, and the body. */
function Answer({ response }: { response: GenLiveResponse }) {
  const { t } = useI18n();
  const ok = response.code < 400;
  const meta = [
    t("gen.live.ms", { ms: response.ms }),
    response.requestId ? t("gen.live.requestId", { id: response.requestId }) : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <div
      className={`rounded-lg border px-3 py-2.5 ${ok ? "border-emerald-200 bg-green-50" : "border-red-200 bg-red-50"}`}
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <span
          className={`rounded px-2 py-px font-mono text-xs font-bold ${
            ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
          }`}
        >
          {response.code}
        </span>
        <span className={`text-xs font-semibold ${ok ? "text-emerald-700" : "text-red-700"}`}>{response.reason}</span>
        <span className="font-mono text-[11px] text-gray-400">{meta}</span>
      </div>
      {response.error && (
        <div className="mt-2 flex flex-col gap-1">
          <span className="text-xs font-semibold text-red-700">{response.error.message}</span>
          <span className="text-pretty text-[11px] leading-normal text-red-900">{response.error.hint}</span>
        </div>
      )}
      <pre className="mt-2 overflow-auto rounded-md bg-gray-900 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-gray-200">
        {JSON.stringify(response.body, null, 2)}
      </pre>
    </div>
  );
}

/**
 * A GET operation in the live check: the row with how its last call went and,
 * opened, the path and query to call it with, the way to send it and OTC's answer.
 */
function LiveOperation({
  op,
  resource,
  open,
  onToggle,
  inputs,
  onInput,
  run,
  onSend,
  against,
}: {
  op: GenOperation;
  resource: string;
  open: boolean;
  onToggle: () => void;
  inputs: Inputs | undefined;
  onInput: (group: keyof Inputs, param: string, value: string) => void;
  run: Run | undefined;
  onSend: () => void;
  against: string;
}) {
  const { t } = useI18n();
  const { method, uri } = op.endpoint;
  const path = pathParams(uri);
  /* the path opens where there is one to fill in, the query stays folded - as in the prototype */
  const [pathOpen, setPathOpen] = useState(true);
  const [queryOpen, setQueryOpen] = useState(false);
  const sdk = `${resource}.${op.sdkMethod}()`;
  const sending = run?.sending ?? false;
  const response = run?.response ?? null;
  const status: CallStatus = sending ? "sending" : response ? (response.code < 400 ? "ok" : "failed") : "none";
  const query = Object.entries(queryValues(op, inputs))
    .map(([param, value]) => `${param}=${encodeURIComponent(value)}`)
    .join("&");

  return (
    <div role="group" aria-label={sdk} className="border-b border-gray-100 last:border-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left"
      >
        {open ? (
          <ChevronDown size={13} className="shrink-0 text-gray-400" />
        ) : (
          <ChevronRight size={13} className="shrink-0 text-gray-400" />
        )}
        <span
          className={`inline-block w-14 shrink-0 rounded px-1.5 py-0.5 text-center font-mono text-[11px] font-semibold ${methodCls(method)}`}
        >
          {method}
        </span>
        <span className="font-mono text-xs font-semibold text-gray-800">{sdk}</span>
        <span className="min-w-0 truncate font-mono text-[11px] text-gray-400" title={uri}>
          {uri}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-px text-[10px] font-semibold uppercase tracking-wide ${CALL_CLS[status]}`}
          >
            {status === "sending" && <Loader2 size={11} className="animate-spin" />}
            {status === "ok" && <Check size={11} />}
            {status === "failed" && <AlertTriangle size={11} />}
            {t(`gen.live.status.${status}` as MessageKey)}
          </span>
          {response && !sending && (
            <span className="font-mono text-[10px] text-gray-300">{t("gen.live.ms", { ms: response.ms })}</span>
          )}
        </span>
      </button>

      {open && (
        <div className="flex flex-wrap items-start gap-5 border-t border-gray-100 bg-gray-50 py-3 pl-10 pr-4">
          <div className="flex min-w-0 flex-[1_1_340px] flex-col gap-1.5">
            {path.length > 0 && (
              <ParamGroup
                label={t("gen.live.path")}
                summary={t("gen.live.params", { n: path.length })}
                open={pathOpen}
                onToggle={() => setPathOpen(!pathOpen)}
              >
                {path.map((param) => (
                  <label key={param} className="flex items-center gap-2">
                    <span className="w-[104px] shrink-0 truncate font-mono text-[11px] text-gray-600">{param}</span>
                    <input
                      aria-label={param}
                      value={inputs?.path[param] ?? ""}
                      onChange={(e) => onInput("path", param, e.target.value)}
                      placeholder={t("gen.live.idOf", { name: param.replace(/_(id|urn)$/, "") })}
                      className={INPUT_CLS}
                    />
                  </label>
                ))}
              </ParamGroup>
            )}
            {op.query.length > 0 && (
              <ParamGroup
                label={t("gen.live.query")}
                summary={query ? `?${query}` : t("gen.live.noneSet", { n: op.query.length })}
                open={queryOpen}
                onToggle={() => setQueryOpen(!queryOpen)}
              >
                {op.query.map((p) => (
                  <label key={p.name} className="flex items-center gap-2">
                    <span
                      className="w-[88px] shrink-0 truncate font-mono text-[11px] text-gray-600"
                      title={t(p.required ? "gen.live.required" : "gen.live.optional", { description: p.description })}
                    >
                      {p.required ? `${p.name} *` : p.name}
                    </span>
                    <span className="w-14 shrink-0 font-mono text-[10px] text-gray-400">{p.type}</span>
                    <input
                      aria-label={p.name}
                      value={inputs?.query[p.name] ?? prefill(p.name)}
                      onChange={(e) => onInput("query", p.name, e.target.value)}
                      className={INPUT_CLS}
                    />
                  </label>
                ))}
              </ParamGroup>
            )}
            <div className="mt-1 flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={onSend}
                disabled={sending}
                className="inline-flex items-center gap-1.5 rounded bg-brand px-3 py-1.5 text-xs font-semibold text-white transition hover:opacity-90 disabled:cursor-default disabled:bg-pink-400 disabled:hover:opacity-100"
              >
                {sending ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                {t(response && !sending ? "gen.live.again" : "gen.live.send")}
              </button>
              <span className="text-[10px] text-gray-400">{against}</span>
            </div>
          </div>

          <div className="min-w-0 flex-[1_1_340px]">
            {sending ? null : response ? (
              <Answer response={response} />
            ) : (
              <div className="rounded-lg border border-dashed border-gray-200 bg-white px-4 py-7 text-center text-[11px] text-gray-400">
                {t("gen.live.empty")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Result of one resource's generation on one target: its job, and - once the
 * job has opened a pull request - the pull request with its state on GitHub,
 * which can be picked up now rather than at the next scheduled poll, and a live
 * check that calls the generated SDK's operations against the OTC tenant. The
 * live check calls GET operations only, so it creates nothing in the tenant and
 * has nothing to clean up (owner decisions). It changes nothing in the panel
 * either, so it is offered to every role; picking up the pull request's state
 * changes the job, and only a role that may write is offered it. A failed job
 * says what went wrong and offers that role to generate again, which starts a
 * new job on the same terms as Generate on the spec: held by the same reasons,
 * with the first one beside it, and fields left to decide with the way to the
 * spec where they are highlighted (owner decisions). The target rides along in the
 * address; the way back leads to the spec when the result was opened from it,
 * and to the card otherwise, as in the prototype.
 */
export function GenerationResultPage() {
  const { name = "", version = "", resource: id = "" } = useParams();
  const [searchParams] = useSearchParams();
  const { state: navState } = useLocation();
  /* The list's state, when the card was opened from it, goes back with the way back. */
  const { fromSpec = false, ...fromList } = (navState ?? {}) as Partial<FromSpec>;
  const { t, locale } = useI18n();
  const { canWrite } = useSession();
  const targets = useGenerationTargets();
  const services = useGenerationServices();
  const resources = useGenerationResources(name);
  const spec = useGenerationSpec(name, id);
  const settings = useOtcSettings();
  const refresh = useRefreshPullRequest(name, id);
  const retry = useStartGeneration(name, id);
  const call = useLiveCall(name, id);
  /* One operation open at a time, none at first - as in the prototype. */
  const [openOp, setOpenOp] = useState<string | null>(null);
  const [inputs, setInputs] = useState<Record<string, Inputs>>({});
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [refused, setRefused] = useState<Error | null>(null);

  const listTo = listPath(fromList);
  const loading = <ServiceLoading />;
  const failed = (
    <ServiceLoadFailed
      back={listTo}
      backState={fromList}
      onRetry={() => {
        for (const q of [targets, services, resources, spec, settings]) if (q.isError) void q.refetch();
      }}
    />
  );

  if (targets.isPending || services.isPending) return loading;
  if (targets.isError || services.isError) return failed;
  if (!services.data.some((s) => s.name === name)) {
    return <PageNotFound back={<ServiceBackLink to={listTo} state={fromList} />} />;
  }
  if (resources.isPending) return loading;
  if (resources.isError) return failed;

  const [defaultTarget] = targets.data;
  const target = targets.data.find((x) => x.id === searchParams.get("target")) ?? defaultTarget;
  const pathTo = (rest: string[] = []) => servicePath(name, target, defaultTarget, rest);
  const resource = resources.data.find((r) => r.id === id && r.version === version);
  const job = resource?.jobs[target.id];
  const back =
    resource && fromSpec ? (
      <ServiceBackLink
        to={pathTo(["spec", resource.version, resource.id])}
        state={fromList}
        label={t("gen.result.backToSpec", { name: resource.name })}
      />
    ) : (
      <ServiceBackLink to={pathTo()} state={fromList} label={t("gen.spec.back", { name })} />
    );
  /* never generated on this target: there is no result to show */
  if (!resource || !job) return <PageNotFound back={back} />;
  if (spec.isPending || settings.isPending) return loading;
  if (spec.isError || settings.isError) return failed;

  const { operations, classes } = spec.data;
  const pkg = name.replaceAll("-", "_");
  const jobState = JOB_STATE[job.status];
  const inReview = job.status === "done";
  const merged = job.status === "merged";
  const at = (iso: string) => fmtSnapshotAt(iso, locale);
  const summary =
    job.status === "running"
      ? t("gen.result.startedNow")
      : job.status === "failed"
        ? [t("gen.result.job", { id: job.id }), t("gen.result.startedBy", { by: job.startedBy, at: at(job.startedAt) })].join(
            " · ",
          )
        : [
            t("gen.result.methods", { n: operations.length }),
            t("gen.spec.classes", { n: classes.length }),
            t("gen.result.generatedBy", { by: job.startedBy, at: at(job.startedAt) }),
            job.mergedBy != null && job.mergedAt != null
              ? t("gen.result.mergedBy", { by: job.mergedBy, at: at(job.mergedAt) })
              : null,
          ]
            .filter(Boolean)
            .join(" · ");
  const live = operations.filter((o) => o.endpoint.method === "GET");
  const hold = holdOf(resource, target, targets.data);
  const open = classes.reduce((n, c) => n + c.fields.filter(undecided).length, 0);
  const refusal = refresh.error ?? retry.error ?? refused;

  const type = (key: string, group: keyof Inputs, param: string, value: string) =>
    setInputs((all) => {
      const current = all[key] ?? { path: {}, query: {} };
      return { ...all, [key]: { ...current, [group]: { ...current[group], [param]: value } } };
    });
  /* The answer before stays until the next one is in - or comes back, if the call is refused. */
  const settle = (key: string, response: GenLiveResponse | null) =>
    setRuns((all) => ({ ...all, [key]: { sending: false, response: response ?? all[key]?.response ?? null } }));
  const send = (op: GenOperation) => {
    const key = op.endpoint.id;
    if (runs[key]?.sending) return;
    const typed = inputs[key];
    setRuns((all) => ({ ...all, [key]: { sending: true, response: all[key]?.response ?? null } }));
    call
      .mutateAsync({
        target: target.id,
        endpoint: key,
        path: Object.fromEntries(pathParams(op.endpoint.uri).map((param) => [param, typed?.path[param] ?? ""])),
        query: queryValues(op, typed),
      })
      .then(
        (response) => settle(key, response),
        (error: Error) => {
          settle(key, null);
          setRefused(error);
        },
      );
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      {back}

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="font-mono text-xl font-semibold text-gray-900">
              {pkg}.{resource.name}
            </h1>
            <StatusPill
              cls={GEN_STATE_CLS[jobState]}
              label={t(genStateKey(jobState))}
              running={jobState === "in_progress"}
            />
            <span className="rounded-full border border-pink-300 bg-pink-50 px-2 py-px text-[10px] font-semibold uppercase tracking-wide text-brand">
              {target.label}
            </span>
          </div>
          <div className="mt-1 text-xs text-gray-400">{summary}</div>
        </div>
        {(inReview || merged) && job.pr != null && (
          <div className="flex flex-wrap items-center gap-2.5">
            <a
              href={`https://github.com/${target.repo}/pull/${job.pr}`}
              target="_blank"
              rel="noreferrer"
              title={t("gen.result.prTitle", { resource: resource.name, pkg, version: resource.version })}
              className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-brand"
            >
              <GitPullRequest size={14} /> {t("gen.result.pr", { pr: job.pr })} <ExternalLink size={12} />
            </a>
            <span
              className={`rounded-full border px-2 py-px text-[10px] font-semibold uppercase tracking-wide ${
                merged ? "border-violet-200 bg-violet-50 text-violet-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"
              }`}
            >
              {t(merged ? "gen.result.prMerged" : "gen.result.prOpen")}
            </span>
            {inReview && canWrite && (
              <button
                type="button"
                title={t("gen.result.refreshHint")}
                disabled={refresh.isPending}
                onClick={() => refresh.mutate(target.id)}
                className="inline-flex items-center gap-1.5 rounded border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500 disabled:cursor-default disabled:text-gray-300 disabled:hover:border-gray-300"
              >
                <RefreshCw size={12} /> {t("gen.result.refresh")}
              </button>
            )}
          </div>
        )}
      </div>

      {refusal && (
        <RefusalBanner
          title={t(mutationErrorKey(refusal))}
          message={refusal.message}
          onDismiss={() => {
            refresh.reset();
            retry.reset();
            setRefused(null);
          }}
        />
      )}

      {job.status === "running" && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 px-6 py-10 text-center">
          <div className="flex items-center justify-center gap-2 text-sm font-semibold text-blue-700">
            <Loader2 size={15} className="animate-spin" /> {t("gen.result.running", { id: job.id })}
          </div>
          <div className="mt-1.5 text-xs text-blue-500">{t("gen.result.runningHint")}</div>
        </div>
      )}

      {job.status === "failed" && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-red-700">
            <AlertTriangle size={14} /> {t("gen.result.failed")}
          </div>
          {job.error && <div className="mt-1.5 font-mono text-[11px] text-red-900">{job.error}</div>}
          <div className="mt-2 max-w-[640px] text-pretty text-xs leading-normal text-red-900">
            {t("gen.result.failedHint")}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3 empty:hidden">
            {canWrite && (
              <button
                type="button"
                disabled={hold != null || open > 0 || retry.isPending}
                onClick={() => retry.mutate(target.id)}
                className="inline-flex items-center gap-1.5 rounded border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 transition hover:border-red-500 disabled:cursor-not-allowed disabled:text-red-300 disabled:hover:border-red-300"
              >
                <RefreshCw size={12} /> {t("gen.result.retry")}
              </button>
            )}
            <HoldReason
              hold={hold}
              open={open}
              target={target}
              layoutTo={pathTo(["layout"])}
              specTo={pathTo(["spec", resource.version, resource.id])}
              state={fromList}
            />
          </div>
        </div>
      )}

      {(inReview || merged) && (
        <>
          {merged && (
            <div className="mb-4 flex flex-wrap items-center gap-2.5 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2.5 text-xs text-violet-700">
              <ClipboardCheck size={14} /> {t("gen.result.mergedNote")}
            </div>
          )}
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">{t("gen.live.title")}</span>
            <span className="text-[10px] text-gray-400">{t("gen.live.hint")}</span>
            <button
              type="button"
              onClick={() => live.forEach(send)}
              className="ml-auto inline-flex items-center gap-1.5 rounded border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500"
            >
              <Play size={12} /> {t("gen.live.runAll")}
            </button>
          </div>
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            {live.map((op) => {
              const key = op.endpoint.id;
              return (
                <LiveOperation
                  key={key}
                  op={op}
                  resource={resource.name}
                  open={openOp === key}
                  onToggle={() => setOpenOp(openOp === key ? null : key)}
                  inputs={inputs[key]}
                  onInput={(group, param, value) => type(key, group, param, value)}
                  run={runs[key]}
                  onSend={() => send(op)}
                  against={t("gen.live.against", { pkg, region: settings.data.region })}
                />
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
