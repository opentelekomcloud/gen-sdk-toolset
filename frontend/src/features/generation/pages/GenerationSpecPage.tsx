import { useState } from "react";
import { AlertTriangle, Check, ExternalLink, Play } from "lucide-react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import {
  useGenerationResources,
  useGenerationServices,
  useGenerationSpec,
  useGenerationTargets,
  useMockGenerationSpec,
} from "../data/queries";
import { useChooseType, useStartGeneration } from "../data/mutations";
import type { GenField, GenOperationKind } from "../data/types";
import type { OperationKind } from "../../../shared/api/types";
import { blockOf, retryJoining } from "../../scan/api/queries";
import { HoldReason } from "../components/HoldReason";
import { JobTag } from "../components/JobTag";
import { LayoutBadge } from "../components/LayoutBadge";
import { NoTargets } from "../components/NoTargets";
import { OperationRow } from "../components/OperationRow";
import { PageMessage } from "../components/PageMessage";
import { PageNotFound } from "../components/PageNotFound";
import { SHOW_GEN_JOBS, SHOW_GEN_RESULT } from "../flags";
import { holdOf, undecided } from "../lib/layout";
import { chosenTarget, listPath, servicePath, type FromSpec } from "../lib/paths";
import {
  RefusalBanner,
  ServiceBackLink,
  ServiceLoadFailed,
  ServiceLoading,
} from "../../scan/components/ServicePageStates";
import { isNotFound } from "../../scan/api/client";
import { mutationErrorKey } from "../../scan/lib/errors";
import { fmtSnapshotAt } from "../../scan/lib/snapshot";
import { useSession } from "../../../shared/auth/useSession";
import { useI18n, type MessageKey } from "../../../shared/i18n";

function SectionTitle({ label, hint }: { label: string; hint: string }) {
  return (
    <div className="mb-2 flex items-baseline gap-2">
      <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">{label}</span>
      <span className="text-[10px] text-gray-400">{hint}</span>
    </div>
  );
}

function OperationColumns() {
  const { t } = useI18n();
  return (
    <div className="grid grid-cols-12 gap-3 border-b border-gray-200 bg-gray-50 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
      <div className="col-span-3">{t("gen.spec.ops.col.operation")}</div>
      <div className="col-span-2">{t("gen.spec.ops.col.kind")}</div>
      <div className="col-span-4">{t("gen.spec.ops.col.endpoint")}</div>
      <div className="col-span-3">{t("gen.spec.ops.col.sdk")}</div>
    </div>
  );
}

function specSummary(
  t: ReturnType<typeof useI18n>["t"],
  n: { target: string; version: string; operations: number; base: number; custom: number; classes: number },
) {
  return [
    t("gen.spec.heading", { target: n.target }),
    n.version,
    t("gen.spec.operations", { n: n.operations }),
    t("gen.spec.base", { n: n.base }),
    t("gen.spec.custom", { n: n.custom }),
    t("gen.spec.classes", { n: n.classes }),
  ].join(" · ");
}

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
 *
 * TODO(#150): the prototype behind `SHOW_GEN_JOBS`; delete with the mock.
 */
function PrototypeSpecPage() {
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
  const spec = useMockGenerationSpec(name, id);
  const choose = useChooseType(name, id);
  const generate = useStartGeneration(name, id);
  /* One problem open at a time, none at first - as in the prototype. */
  const [openIssue, setOpenIssue] = useState<string | null>(null);

  /* Each block by the one rule (ADR-0081); a Retry joins a request already asking (ADR-0084). */
  const targetsBlock = blockOf(targets);
  const servicesBlock = blockOf(services);
  const resourcesBlock = blockOf(resources);
  const specBlock = blockOf(spec);

  const listTo = listPath(fromList);
  const loading = <ServiceLoading />;
  const failed = (
    <ServiceLoadFailed
      back={listTo}
      backState={fromList}
      onRetry={() => {
        if (targetsBlock.failed) void retryJoining(targets);
        if (servicesBlock.failed) void retryJoining(services);
        if (resourcesBlock.failed) void retryJoining(resources);
        if (specBlock.failed) void retryJoining(spec);
      }}
    />
  );

  if (targetsBlock.failed || servicesBlock.failed) return failed;
  if (targetsBlock.pending || servicesBlock.pending) return loading;
  if (!servicesBlock.data.some((s) => s.name === name)) {
    return <PageNotFound back={<ServiceBackLink to={listTo} state={fromList} />} />;
  }
  if (resourcesBlock.failed) return failed;
  if (resourcesBlock.pending) return loading;

  const chosen = chosenTarget(targetsBlock.data, searchParams.get("target"));
  if (!chosen) return <NoTargets back={listTo} backState={fromList} targets={targets} />;
  const { target, defaultTarget } = chosen;
  const pathTo = (rest: string[] = []) => servicePath(name, target, defaultTarget, rest);
  const back = <ServiceBackLink to={pathTo()} state={fromList} label={t("gen.spec.back", { name })} />;
  const resource = resourcesBlock.data.find((r) => r.id === id && r.version === version);
  if (!resource) return <PageNotFound back={back} />;
  if (specBlock.failed) return failed;
  if (specBlock.pending) return loading;

  const { operations, classes } = specBlock.data;
  const open = classes.reduce((n, c) => n + c.fields.filter(undecided).length, 0);
  const job = resource.jobs[target.id];
  const hold = holdOf(resource, target, targetsBlock.data);
  const resultTo = pathTo(["result", resource.version, resource.id]);
  const toResult = { ...fromList, fromSpec: true } satisfies FromSpec;
  const summary = specSummary(t, {
    target: target.label,
    version: resource.version,
    operations: operations.length,
    base: operations.filter((o) => o.kind === "base").length,
    custom: operations.filter((o) => o.kind === "custom").length,
    classes: classes.length,
  });
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
            <LayoutBadge confirmed={resource.confirmedBy != null} origin={resource.origin} />
          </div>
          <div className="mt-1 text-xs text-gray-400">{summary}</div>
        </div>
        {job ? (
          <JobTag job={job} to={resultTo} state={toResult} />
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <HoldReason hold={hold} open={open} layoutTo={pathTo(["layout"])} state={fromList} />
            {canWrite && (
              <button
                type="button"
                disabled={hold != null || open > 0 || generate.isPending}
                onClick={() =>
                  generate.mutate(target.id, {
                    /* The result page is PageNotFound while it is switched off
                       (ADR-0086): the spec stays, its job in place of Generate. */
                    onSuccess: () => {
                      if (SHOW_GEN_RESULT) navigate(resultTo, { state: toResult });
                    },
                  })
                }
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

      <SectionTitle label={t("gen.spec.ops")} hint={t("gen.spec.ops.hint")} />
      <div className="mb-6 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <OperationColumns />
        {operations.map(({ endpoint, kind, sdkMethod }) => (
          <OperationRow
            key={endpoint.id}
            title={endpoint.title}
            kind={kind}
            method={endpoint.method}
            uri={endpoint.uri}
            call={`${resource.name}.${sdkMethod}()`}
            href={endpoint.src}
          />
        ))}
      </div>

      <SectionTitle label={t("gen.spec.entities")} hint={t("gen.spec.entities.hint")} />
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

export function GenerationSpecPage() {
  return SHOW_GEN_JOBS ? <PrototypeSpecPage /> : <ServerSpecPage />;
}

const shownKind = (kind: OperationKind): GenOperationKind => (kind === "custom" ? "custom" : "base");

function ServerSpecPage() {
  const { name = "", version = "", resource = "" } = useParams();
  const [searchParams] = useSearchParams();
  const { state: fromList } = useLocation();
  const { t } = useI18n();
  const { canWrite } = useSession();
  /* the route takes a number only, and answers anything else 422 */
  const valid = /^[1-9][0-9]*$/.test(resource);
  const targets = useGenerationTargets();
  const spec = useGenerationSpec(name, version, Number(resource), { enabled: valid });
  const targetsBlock = blockOf(targets);
  const specBlock = blockOf(spec);

  const listTo = listPath(fromList);
  if (!valid || isNotFound(spec.error)) {
    return <PageNotFound back={<ServiceBackLink to={listTo} state={fromList} />} />;
  }
  if (targetsBlock.failed || specBlock.failed) {
    return (
      <ServiceLoadFailed
        back={listTo}
        backState={fromList}
        onRetry={() => {
          if (targetsBlock.failed) void retryJoining(targets);
          if (specBlock.failed) void retryJoining(spec);
        }}
      />
    );
  }
  if (!targetsBlock.data || !specBlock.data) return <ServiceLoading />;

  const chosen = chosenTarget(targetsBlock.data, searchParams.get("target"));
  if (!chosen) return <NoTargets back={listTo} backState={fromList} targets={targets} />;
  const { target, defaultTarget } = chosen;
  const cardTo = servicePath(name, target, defaultTarget);
  const back = <ServiceBackLink to={cardTo} state={fromList} label={t("gen.spec.back", { name })} />;

  const { confirmed, operations, classes } = specBlock.data;
  if (!confirmed || !operations || !classes) {
    /* The way to the layout, where a worker confirms it; a viewer, who may not, only views it (ADR-0133). */
    const label = t(canWrite ? "gen.card.editLayout" : "gen.card.viewLayout");
    return (
      <PageMessage
        back={back}
        note={t("gen.spec.notConfirmed")}
        link={{ to: servicePath(name, target, defaultTarget, ["layout"]), label }}
      />
    );
  }
  if (!target.live) {
    return (
      <PageMessage
        back={back}
        note={t("gen.hold.notConnected", { target: target.label })}
        link={{ to: cardTo, label: t("gen.layout.toCard") }}
      />
    );
  }

  const summary = specSummary(t, {
    target: target.label,
    version,
    operations: operations.length,
    base: operations.filter((o) => shownKind(o.kind) === "base").length,
    custom: operations.filter((o) => shownKind(o.kind) === "custom").length,
    classes: classes.length,
  });

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      {back}

      <div className="mb-4">
        <h1 className="font-mono text-xl font-semibold text-gray-900">
          {name.replaceAll("-", "_")}.{specBlock.data.name}
        </h1>
        <div className="mt-1 text-xs text-gray-400">{summary}</div>
      </div>

      <section aria-label={t("gen.spec.ops")}>
        <SectionTitle label={t("gen.spec.ops")} hint={t("gen.spec.ops.hint")} />
        <div className="mb-6 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <OperationColumns />
          {operations.map((o) => (
            <OperationRow
              key={o.path}
              title={o.title ?? o.path}
              kind={shownKind(o.kind)}
              method={o.method}
              uri={o.uri}
              call={o.name === null ? null : `${specBlock.data.name}.${o.name}()`}
              missing={o.missing_name ? t(`gen.spec.missing.${o.missing_name}`) : undefined}
              href={o.source_url}
            />
          ))}
        </div>
      </section>

      <section aria-label={t("gen.spec.entities")}>
        <SectionTitle label={t("gen.spec.entities")} hint={t("gen.spec.entities.hint")} />
        {/* TODO(ISS-0092): a block for each class. */}
      </section>
    </div>
  );
}
