import { Folder, Play } from "lucide-react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { useGenerationResources, useGenerationServices, useGenerationTargets } from "../data/queries";
import type { GenResource, GenTarget } from "../data/types";
import { HoldReason } from "../components/HoldReason";
import { JobTag } from "../components/JobTag";
import { PageNotFound } from "../components/PageNotFound";
import { holdOf } from "../lib/layout";
import { listPath, servicePath } from "../lib/paths";
import { ServiceBackLink, ServiceLoadFailed, ServiceLoading } from "../../scan/components/ServicePageStates";
import { useI18n } from "../../../shared/i18n";

function ResourceRow({
  resource,
  target,
  targets,
  pathTo,
}: {
  resource: GenResource;
  target: GenTarget;
  targets: GenTarget[];
  pathTo: (rest: string[]) => string;
}) {
  const { t } = useI18n();
  /* the list's state rides on into the layout and the spec, and back */
  const { state: fromList } = useLocation();
  const job = resource.jobs[target.id];
  const endpoints = resource.endpoints.length;
  const hold = holdOf(resource, target, targets);
  const mergedIn = targets
    .filter((x) => x.id !== target.id && resource.jobs[x.id]?.status === "merged")
    .map((x) => x.label);
  const meta = [
    t("gen.card.endpoints", { n: endpoints }),
    resource.confirmedBy != null
      ? t("gen.card.confirmedBy", { by: resource.confirmedBy })
      : t("gen.card.notConfirmed"),
    mergedIn.length ? t("gen.card.mergedIn", { targets: mergedIn.join(", ") }) : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-gray-100 px-4 py-[11px] last:border-0">
      <span className="flex min-w-[200px] flex-auto flex-col gap-[3px] overflow-hidden">
        <span className="truncate font-mono text-sm text-gray-800">{resource.name}</span>
        <span className="text-[11px] text-gray-400">{meta}</span>
      </span>
      {job ? (
        <JobTag job={job} to={pathTo(["result", resource.version, resource.id])} state={fromList} />
      ) : hold === null ? (
        <Link
          to={pathTo(["spec", resource.version, resource.id])}
          state={fromList}
          className="inline-flex shrink-0 items-center gap-1.5 rounded border border-pink-300 bg-pink-50 px-3.5 py-[5px] text-xs font-semibold text-brand transition hover:border-brand"
        >
          <Play size={12} /> {t("gen.card.generate")}
        </Link>
      ) : (
        <HoldReason hold={hold} target={target} layoutTo={pathTo(["layout"])} state={fromList} />
      )}
    </div>
  );
}

/**
 * Service card: one target at a time - coverage of every target, the resources
 * with their state there, and Generate or the reason it is not offered. The
 * layout is shared by every target and only read here; it is edited on its own
 * page. The target round-trips through the address.
 */
export function GenerationServicePage() {
  const { name = "" } = useParams();
  const [searchParams] = useSearchParams();
  /* Opened from the list, the card knows the list's query and search text and leads back to both. */
  const { state: fromList } = useLocation();
  const navigate = useNavigate();
  const { t } = useI18n();
  const targets = useGenerationTargets();
  const services = useGenerationServices();
  const resources = useGenerationResources(name);

  const listTo = listPath(fromList);
  const back = <ServiceBackLink to={listTo} state={fromList} />;
  const loading = <ServiceLoading />;
  const failed = (
    <ServiceLoadFailed
      back={listTo}
      backState={fromList}
      onRetry={() => {
        for (const q of [targets, services, resources]) if (q.isError) void q.refetch();
      }}
    />
  );

  if (targets.isPending || services.isPending) return loading;
  if (targets.isError || services.isError) return failed;
  const service = services.data.find((s) => s.name === name);
  if (!service) return <PageNotFound back={back} />;
  if (resources.isPending) return loading;
  if (resources.isError) return failed;

  const [defaultTarget] = targets.data;
  /* An unknown target falls back to the default, as in the prototype. */
  const target = targets.data.find((x) => x.id === searchParams.get("target")) ?? defaultTarget;
  const labelOf = (id: string | null) => targets.data.find((x) => x.id === id)?.label;
  const base = labelOf(target.base);

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      {back}

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-mono text-xl font-semibold text-gray-900">{name}</h1>
          <div className="mt-1 text-xs text-gray-400">{t("gen.card.generating", { target: target.label })}</div>
        </div>
        <Link
          to={servicePath(name, target, defaultTarget, ["layout"])}
          state={fromList}
          className="inline-flex items-center gap-1.5 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:border-gray-500"
        >
          <Folder size={14} className="text-gray-400" /> {t("gen.card.editLayout")}
        </Link>
      </div>

      <div className="mb-2.5 flex flex-wrap gap-2">
        {targets.data.map((x) => {
          const on = x.id === target.id;
          const { merged, total } = service.targets[x.id];
          const xBase = labelOf(x.base);
          const sub = !x.live
            ? xBase
              ? t("gen.waitsOn", { base: xBase })
              : t("gen.card.planned")
            : total
              ? t("gen.card.merged", { n: merged, total })
              : t("gen.card.noResources");
          return (
            <button
              type="button"
              key={x.id}
              aria-pressed={on}
              onClick={() => navigate(servicePath(name, x, defaultTarget), { replace: true, state: fromList })}
              className={`min-w-0 flex-1 rounded-lg border px-2.5 py-2 text-left transition ${
                on ? "border-brand bg-pink-50" : "border-gray-200 bg-white hover:border-gray-400"
              }`}
            >
              <span className={`block text-[11px] font-semibold ${on ? "text-brand" : "text-gray-500"}`}>{x.label}</span>
              <span className={`mt-[3px] block font-mono text-[11px] ${on ? "text-brand" : "text-gray-400"}`}>{sub}</span>
              <span className={`mt-1.5 block h-[3px] rounded-sm ${on ? "bg-pink-300" : "bg-gray-100"}`}>
                <span
                  className={`block h-[3px] rounded-sm ${on ? "bg-brand" : "bg-gray-300"}`}
                  style={{ width: `${total ? Math.round((merged / total) * 100) : 0}%` }}
                />
              </span>
            </button>
          );
        })}
      </div>
      <div className="mb-4 text-[11px] leading-normal text-gray-500">
        {base
          ? t("gen.card.hint.base", { target: target.label, base })
          : target.live
            ? t("gen.card.hint.repo", { repo: target.repo })
            : t("gen.card.hint.notConnected", { target: target.label })}
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center gap-2.5 border-b border-gray-200 bg-gray-50 px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
          <span>{t("gen.card.col.resource")}</span>
          <span className="ml-auto">{target.label}</span>
        </div>
        {resources.data.map((r) => (
          <ResourceRow
            key={r.id}
            resource={r}
            target={target}
            targets={targets.data}
            pathTo={(rest) => servicePath(name, target, defaultTarget, rest)}
          />
        ))}
        {resources.data.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-gray-400">{t("gen.card.empty")}</div>
        )}
      </div>
    </div>
  );
}
