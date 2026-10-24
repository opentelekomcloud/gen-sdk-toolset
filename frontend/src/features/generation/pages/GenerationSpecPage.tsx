import { ODSButton } from "@telekom-ods/react-ui-kit/ODSButton";
import { useState } from "react";
import { ODSCheckmark, ODSNavigationExternalLink, ODSPlay, ODSWarning } from "@telekom-ods/react-icons";
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
import { holdOf, undecided } from "../lib/layout";
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
  base: "border-info-line bg-info-subtle text-info",
  custom: "border-brand-subtle bg-brand-subtle text-on-brand-subtle",
};

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
  const tone = choice ? "text-success" : "text-warning";

  return (
    <div role="group" aria-label={field.name}>
      <div
        className={`grid grid-cols-12 gap-2 border-b border-neutral-100 px-4 py-1.5 font-mono text-[11px] ${
          undecided(field) ? "bg-warning-subtle" : "bg-surface"
        }`}
      >
        <div className="col-span-3 truncate text-ink" title={field.name}>
          {field.name}
        </div>
        <div
          className={`col-span-3 truncate ${
            unknown ? "font-semibold text-warning" : choice ? "font-semibold text-success" : "text-ink-recessive"
          }`}
          title={type}
        >
          {unknown ? `⚠ ${type}` : type}
        </div>
        <div className="col-span-1 text-neutral-700">{field.required ? t("gen.spec.required") : "—"}</div>
        <div className="col-span-5 flex min-w-0 items-center gap-1.5">
          <span className="truncate text-neutral-600" title={field.description}>
            {field.description}
          </span>
          {issue && (
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={open}
              title={issue.text}
              className={`ml-auto inline-flex shrink-0 items-center gap-1 rounded border bg-surface px-1.5 py-px font-sans text-[10px] font-semibold ${
                choice ? "border-success-line" : "border-warning-line"
              } ${tone}`}
            >
              {choice ? <ODSCheckmark decorative size={11} /> : <ODSWarning decorative size={11} />}
              {choice ? t("gen.spec.resolved") : t(`gen.spec.problem.${issue.problem}` as MessageKey)}
            </button>
          )}
        </div>
      </div>

      {issue && open && (
        <div
          className={`border-b py-2.5 pl-7 pr-4 ${
            choice ? "border-success-line bg-success-subtle" : "border-warning-line bg-warning-subtle"
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
                  <ODSNavigationExternalLink decorative size={11} /> {doc.label}
                </a>
              ))}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-neutral-600">{t("gen.spec.useType")}</span>
            {issue.options.map((option) => {
              const on = choice?.type === option.type;
              const cls = `flex flex-col items-start gap-px rounded-md border bg-surface px-2.5 py-[5px] text-left ${
                on ? "border-success ring-1 ring-success" : "border-neutral-200"
              }`;
              const body = (
                <>
                  <span className={`font-mono text-[11px] font-semibold ${on ? "text-success" : "text-ink"}`}>
                    {option.type}
                  </span>
                  <span className="text-[10px] text-neutral-600">{option.note}</span>
                </>
              );
              /* choosing the chosen type again takes the choice back, as in the prototype */
              return canWrite ? (
                <button
                  key={option.type}
                  type="button"
                  aria-pressed={on}
                  onClick={() => choose(on ? null : option.type)}
                  className={`${cls} transition ${on ? "" : "hover:border-neutral-500"}`}
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
              <span className="text-[10px] text-neutral-700">
                {t("gen.spec.chosenBy", { by: choice.by, at: fmtSnapshotAt(choice.at, locale) })}
              </span>
            )}
            {choice && canWrite && (
              <button
                type="button"
                onClick={() => choose(null)}
                className="ml-auto text-[11px] text-neutral-700 underline decoration-dotted"
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
            <h1 className="font-mono text-xl font-semibold text-ink">
              {name.replaceAll("-", "_")}.{resource.name}
            </h1>
            <LayoutBadge resource={resource} />
          </div>
          <div className="mt-1 text-xs text-neutral-600">{summary}</div>
        </div>
        {job ? (
          <JobTag job={job} to={resultTo} state={toResult} />
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <HoldReason hold={hold} open={open} target={target} layoutTo={pathTo(["layout"])} state={fromList} />
            {canWrite && (
              <ODSButton
                size="small"
                label={t("gen.spec.generate", { target: target.label })}
                buttonIcon={<ODSPlay decorative />}
                leftIcon
                disabled={hold != null || open > 0 || generate.isPending}
                onClick={() => generate.mutate(target.id, { onSuccess: () => navigate(resultTo, { state: toResult }) })}
              />
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
        <span className="text-xs font-semibold uppercase tracking-wider text-neutral-700">{t("gen.spec.ops")}</span>
        <span className="text-[10px] text-neutral-600">{t("gen.spec.ops.hint")}</span>
      </div>
      <div className="mb-6 overflow-hidden rounded-xl border border-neutral-200 bg-surface shadow-sm">
        <div className="grid grid-cols-12 gap-3 border-b border-neutral-200 bg-neutral-50 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-neutral-700">
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
            className="grid grid-cols-12 items-center gap-3 border-b border-neutral-100 px-4 py-2 last:border-0"
          >
            <div className="col-span-3 truncate text-xs text-ink-recessive" title={endpoint.title}>
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
              <span className="truncate font-mono text-[11px] text-neutral-700" title={endpoint.uri}>
                {endpoint.uri}
              </span>
            </div>
            <div className="col-span-3 flex min-w-0 items-center gap-2">
              <span className="truncate font-mono text-[11px] text-ink">
                {resource.name}.{sdkMethod}()
              </span>
              <a
                href={endpoint.src}
                target="_blank"
                rel="noreferrer"
                title={t("doc.openSourceHint")}
                className="ml-auto flex items-center text-neutral-600 transition hover:text-ink-recessive"
              >
                <ODSNavigationExternalLink decorative size={13} />
              </a>
            </div>
          </div>
        ))}
      </div>

      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-neutral-700">{t("gen.spec.entities")}</span>
        <span className="text-[10px] text-neutral-600">{t("gen.spec.entities.hint")}</span>
      </div>
      {classes.map((c) => {
        const toDecide = c.fields.filter(undecided).length;
        return (
          <section
            key={c.name}
            aria-label={c.name}
            className="mb-3 overflow-hidden rounded-xl border border-neutral-200 bg-surface shadow-sm"
          >
            <div className="flex items-center gap-2.5 border-b border-neutral-200 bg-neutral-50 px-4 py-2.5">
              <span className="font-mono text-sm font-semibold text-ink">{c.name}</span>
              <span className="font-mono text-xs text-neutral-600">{t("gen.spec.fields", { n: c.fields.length })}</span>
              {toDecide > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full border border-warning-line bg-warning-subtle px-2 py-px text-[10px] font-semibold text-warning">
                  <ODSWarning decorative size={11} /> {t("gen.spec.toDecide", { n: toDecide })}
                </span>
              )}
            </div>
            <div className="grid grid-cols-12 gap-2 border-b border-neutral-200 bg-neutral-100 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-700">
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
