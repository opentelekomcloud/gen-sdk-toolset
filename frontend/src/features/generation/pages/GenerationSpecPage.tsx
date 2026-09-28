import { useState } from "react";
import { AlertTriangle, Check, ExternalLink, Play } from "lucide-react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import {
  useGenerationResources,
  useGenerationServices,
  useGenerationSpec,
  useGenerationTargets,
} from "../data/queries";
import { useChooseType, useStartGeneration } from "../data/mutations";
import type { GenField, GenOperationKind } from "../data/types";
import { HoldReason } from "../components/HoldReason";
import { JobTag } from "../components/JobTag";
import { LayoutBadge } from "../components/LayoutBadge";
import { PageNotFound } from "../components/PageNotFound";
import { holdOf } from "../lib/layout";
import { listPath, servicePath, type FromSpec } from "../lib/paths";
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

const KIND_CLS: Record<GenOperationKind, string> = {
  base: "border-blue-200 bg-blue-50 text-blue-700",
  custom: "border-purple-200 bg-purple-50 text-purple-700",
};

/** A field whose problem nobody has decided yet. */
const undecided = (f: GenField) => f.issue != null && f.issue.choice == null;

/**
 * A field of a class, and under it - when opened - its problem: what is wrong,
 * the documents it comes from, the types to choose from and who chose one.
 */
function FieldRow({
  field,
  open,
  onToggle,
  canWrite,
  choose,
}: {
  field: GenField;
  open: boolean;
  onToggle: () => void;
  canWrite: boolean;
  choose: (type: string | null) => void;
}) {
  const { t, locale } = useI18n();
  const { issue } = field;
  const choice = issue?.choice ?? null;
  const unknown = undecided(field) && issue?.problem === "unknown_type";
  const type = choice?.type ?? field.type;
  const tone = choice ? "text-emerald-700" : "text-amber-800";

  return (
    <div role="group" aria-label={field.name}>
      <div
        className={`grid grid-cols-12 gap-2 border-b border-gray-100 px-4 py-1.5 font-mono text-[11px] ${
          undecided(field) ? "bg-amber-50" : "bg-white"
        }`}
      >
        <div className="col-span-3 truncate text-gray-800" title={field.name}>
          {field.name}
        </div>
        <div
          className={`col-span-3 truncate ${
            unknown ? "font-semibold text-amber-700" : choice ? "font-semibold text-emerald-700" : "text-gray-600"
          }`}
          title={type}
        >
          {unknown ? `⚠ ${type}` : type}
        </div>
        <div className="col-span-1 text-gray-500">{field.required ? t("gen.spec.required") : "—"}</div>
        <div className="col-span-5 flex min-w-0 items-center gap-1.5">
          <span className="truncate text-gray-400" title={field.description}>
            {field.description}
          </span>
          {issue && (
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={open}
              title={issue.text}
              className={`ml-auto inline-flex shrink-0 items-center gap-1 rounded border bg-white px-1.5 py-px font-sans text-[10px] font-semibold ${
                choice ? "border-emerald-200" : "border-amber-200"
              } ${tone}`}
            >
              {choice ? <Check size={11} /> : <AlertTriangle size={11} />}
              {choice ? t("gen.spec.resolved") : t(`gen.spec.problem.${issue.problem}` as MessageKey)}
            </button>
          )}
        </div>
      </div>

      {issue && open && (
        <div
          className={`border-b py-2.5 pl-7 pr-4 ${
            choice ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"
          }`}
        >
          <div className="flex flex-wrap items-center gap-2.5">
            <span className={`max-w-[640px] text-pretty text-[11px] leading-normal ${tone}`}>{issue.text}</span>
            <span className="ml-auto flex flex-wrap gap-2.5">
              {issue.docs.map((doc) => (
                <a
                  key={doc.src}
                  href={doc.src}
                  target="_blank"
                  rel="noreferrer"
                  className={`inline-flex items-center gap-1 text-[11px] font-medium ${tone}`}
                >
                  <ExternalLink size={11} /> {doc.label}
                </a>
              ))}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{t("gen.spec.useType")}</span>
            {issue.options.map((option) => {
              const on = choice?.type === option.type;
              const cls = `flex flex-col items-start gap-px rounded-md border bg-white px-2.5 py-[5px] text-left ${
                on ? "border-emerald-700 ring-1 ring-emerald-700" : "border-gray-200"
              }`;
              const body = (
                <>
                  <span className={`font-mono text-[11px] font-semibold ${on ? "text-emerald-700" : "text-gray-800"}`}>
                    {option.type}
                  </span>
                  <span className="text-[10px] text-gray-400">{option.note}</span>
                </>
              );
              /* choosing the chosen type again takes the choice back, as in the prototype */
              return canWrite ? (
                <button
                  key={option.type}
                  type="button"
                  aria-pressed={on}
                  onClick={() => choose(on ? null : option.type)}
                  className={`${cls} transition ${on ? "" : "hover:border-gray-400"}`}
                >
                  {body}
                </button>
              ) : (
                <span key={option.type} className={cls}>
                  {body}
                </span>
              );
            })}
            {choice && (
              <span className="text-[10px] text-gray-500">
                {t("gen.spec.chosenBy", { by: choice.by, at: fmtSnapshotAt(choice.at, locale) })}
              </span>
            )}
            {choice && canWrite && (
              <button
                type="button"
                onClick={() => choose(null)}
                className="ml-auto text-[11px] text-gray-500 underline decoration-dotted"
              >
                {t("gen.spec.clear")}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Generation spec of one resource on one target: the operations its endpoints
 * become, and the classes the generator will emit. A field whose type the docs
 * leave open is decided here, with who and when. Generate is held by what holds
 * it on the card and, after that, by a field left open (owner decisions), with
 * the first reason beside it; a resource already generated on the target shows
 * its job instead, as on the card. The prototype's dependencies block is gone
 * (owner decision). The target rides along in the address.
 */
export function GenerationSpecPage() {
  const { name = "", version = "", resource: id = "" } = useParams();
  const [searchParams] = useSearchParams();
  /* The list's state, when the card was opened from it: it goes back with the way back. */
  const { state: fromList } = useLocation();
  const navigate = useNavigate();
  const { t } = useI18n();
  const { canWrite } = useSession();
  const targets = useGenerationTargets();
  const services = useGenerationServices();
  const resources = useGenerationResources(name);
  const spec = useGenerationSpec(name, id);
  const choose = useChooseType(name, id);
  const generate = useStartGeneration(name, id);
  /* One problem open at a time, none at first - as in the prototype. */
  const [openIssue, setOpenIssue] = useState<string | null>(null);

  const listTo = listPath(fromList);
  const loading = <ServiceLoading />;
  const failed = (
    <ServiceLoadFailed
      back={listTo}
      backState={fromList}
      onRetry={() => {
        for (const q of [targets, services, resources, spec]) if (q.isError) void q.refetch();
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
  const back = <ServiceBackLink to={pathTo()} state={fromList} label={t("gen.spec.back", { name })} />;
  const resource = resources.data.find((r) => r.id === id && r.version === version);
  if (!resource) return <PageNotFound back={back} />;
  if (spec.isPending) return loading;
  if (spec.isError) return failed;

  const { operations, classes } = spec.data;
  const open = classes.reduce((n, c) => n + c.fields.filter(undecided).length, 0);
  const job = resource.jobs[target.id];
  const hold = holdOf(resource, target, targets.data);
  const resultTo = pathTo(["result", resource.version, resource.id]);
  const toResult = { ...fromList, fromSpec: true } satisfies FromSpec;
  const summary = [
    t("gen.spec.heading", { target: target.label }),
    resource.version,
    t("gen.spec.operations", { n: operations.length }),
    t("gen.spec.base", { n: operations.filter((o) => o.kind === "base").length }),
    t("gen.spec.custom", { n: operations.filter((o) => o.kind === "custom").length }),
    t("gen.spec.classes", { n: classes.length }),
  ].join(" · ");
  const refusal = [generate, choose].find((m) => m.isError);

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      {back}

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="font-mono text-xl font-semibold text-gray-900">
              {name.replaceAll("-", "_")}.{resource.name}
            </h1>
            <LayoutBadge resource={resource} />
          </div>
          <div className="mt-1 text-xs text-gray-400">{summary}</div>
        </div>
        {job ? (
          <JobTag job={job} to={resultTo} state={toResult} />
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            {hold ? (
              <HoldReason hold={hold} target={target} layoutTo={pathTo(["layout"])} state={fromList} />
            ) : (
              open > 0 && <span className="text-[11px] text-gray-400">{t("gen.spec.decideFirst", { n: open })}</span>
            )}
            {canWrite && (
              <button
                type="button"
                disabled={hold != null || open > 0 || generate.isPending}
                onClick={() => generate.mutate(target.id, { onSuccess: () => navigate(resultTo, { state: toResult }) })}
                className="inline-flex items-center gap-1.5 rounded border border-transparent bg-brand px-3.5 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:border-gray-200 disabled:bg-gray-50 disabled:text-gray-300 disabled:hover:opacity-100"
              >
                <Play size={14} /> {t("gen.spec.generate", { target: target.label })}
              </button>
            )}
          </div>
        )}
      </div>

      {refusal?.error && (
        <RefusalBanner
          title={t(mutationErrorKey(refusal.error))}
          message={refusal.error.message}
          onDismiss={() => refusal.reset()}
        />
      )}

      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">{t("gen.spec.ops")}</span>
        <span className="text-[10px] text-gray-400">{t("gen.spec.ops.hint")}</span>
      </div>
      <div className="mb-6 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="grid grid-cols-12 gap-3 border-b border-gray-200 bg-gray-50 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
          <div className="col-span-3">{t("gen.spec.ops.col.operation")}</div>
          <div className="col-span-2">{t("gen.spec.ops.col.kind")}</div>
          <div className="col-span-4">{t("gen.spec.ops.col.endpoint")}</div>
          <div className="col-span-3">{t("gen.spec.ops.col.sdk")}</div>
        </div>
        {operations.map(({ endpoint, kind, sdkMethod }) => (
          <div
            key={endpoint.id}
            role="group"
            aria-label={endpoint.title}
            className="grid grid-cols-12 items-center gap-3 border-b border-gray-100 px-4 py-2 last:border-0"
          >
            <div className="col-span-3 truncate text-xs text-gray-600" title={endpoint.title}>
              {endpoint.title}
            </div>
            <div className="col-span-2">
              <span
                className={`rounded-full border px-2 py-px text-[10px] font-semibold uppercase tracking-wide ${KIND_CLS[kind]}`}
              >
                {t(`gen.spec.kind.${kind}` as MessageKey)}
              </span>
            </div>
            <div className="col-span-4 flex min-w-0 items-center gap-2">
              <span
                className={`inline-block w-14 shrink-0 rounded px-1.5 py-0.5 text-center font-mono text-[11px] font-semibold ${methodCls(endpoint.method)}`}
              >
                {endpoint.method}
              </span>
              <span className="truncate font-mono text-[11px] text-gray-500" title={endpoint.uri}>
                {endpoint.uri}
              </span>
            </div>
            <div className="col-span-3 flex min-w-0 items-center gap-2">
              <span className="truncate font-mono text-[11px] text-gray-800">
                {resource.name}.{sdkMethod}()
              </span>
              <a
                href={endpoint.src}
                target="_blank"
                rel="noreferrer"
                title={t("doc.openSourceHint")}
                className="ml-auto flex items-center text-gray-400 transition hover:text-gray-700"
              >
                <ExternalLink size={13} />
              </a>
            </div>
          </div>
        ))}
      </div>

      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">{t("gen.spec.entities")}</span>
        <span className="text-[10px] text-gray-400">{t("gen.spec.entities.hint")}</span>
      </div>
      {classes.map((c) => {
        const toDecide = c.fields.filter(undecided).length;
        return (
          <section
            key={c.name}
            aria-label={c.name}
            className="mb-3 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm"
          >
            <div className="flex items-center gap-2.5 border-b border-gray-200 bg-gray-50 px-4 py-2.5">
              <span className="font-mono text-sm font-semibold text-gray-900">{c.name}</span>
              <span className="font-mono text-xs text-gray-400">{t("gen.spec.fields", { n: c.fields.length })}</span>
              {toDecide > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-px text-[10px] font-semibold text-amber-800">
                  <AlertTriangle size={11} /> {t("gen.spec.toDecide", { n: toDecide })}
                </span>
              )}
            </div>
            <div className="grid grid-cols-12 gap-2 border-b border-gray-200 bg-gray-100 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
              <div className="col-span-3">{t("gen.spec.col.field")}</div>
              <div className="col-span-3">{t("gen.spec.col.type")}</div>
              <div className="col-span-1">{t("gen.spec.col.req")}</div>
              <div className="col-span-5">{t("gen.spec.col.description")}</div>
            </div>
            {c.fields.map((f) => {
              const key = `${c.name}.${f.name}`;
              return (
                <FieldRow
                  key={f.name}
                  field={f}
                  open={openIssue === key}
                  onToggle={() => setOpenIssue(openIssue === key ? null : key)}
                  canWrite={canWrite}
                  choose={(type) => choose.mutate({ cls: c.name, field: f.name, type })}
                />
              );
            })}
          </section>
        );
      })}
    </div>
  );
}
