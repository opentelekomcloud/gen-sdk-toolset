import { Folder, LayoutGrid, Play } from "lucide-react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import type { ReactNode } from "react";
import { useGenerationLayout, useGenerationResources, useGenerationTargets, useInGeneration } from "../data/queries";
import { useStartLayout } from "../data/mutations";
import type { GenResource, GenTarget } from "../data/types";
import type { Layout, LayoutResource } from "../../../shared/api/types";
import { HoldReason } from "../components/HoldReason";
import { JobTag } from "../components/JobTag";
import { NoTargets } from "../components/NoTargets";
import { PageNotFound } from "../components/PageNotFound";
import { connectionHold, holdOf, layoutHold } from "../lib/layout";
import { chosenTarget, listPath, servicePath } from "../lib/paths";
import { SHOW_GEN_JOBS } from "../flags";
import { isNotFound } from "../../scan/api/client";
import { mutationErrorKey } from "../../scan/lib/errors";
import { blockOf, retryJoining } from "../../scan/api/queries";
import {
  BlockLoadFailed,
  BlockLoading,
  ServiceBackLink,
  ServiceLoadFailed,
  ServiceLoading,
} from "../../scan/components/ServicePageStates";
import { useSession } from "../../../shared/auth/useSession";
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
  const { canWrite } = useSession();
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
        /* Generate leads to starting a job, which a viewer may not (ADR-0070);
           the jobs and the reasons a resource waits stay for every role. */
        canWrite && (
          <Link
            to={pathTo(["spec", resource.version, resource.id])}
            state={fromList}
            className="inline-flex shrink-0 items-center gap-1.5 rounded border border-pink-300 bg-pink-50 px-3.5 py-[5px] text-xs font-semibold text-brand transition hover:border-brand"
          >
            <Play size={12} /> {t("gen.card.generate")}
          </Link>
        )
      ) : (
        <HoldReason hold={hold} layoutTo={pathTo(["layout"])} state={fromList} />
      )}
    </div>
  );
}

/**
 * The repo as the title, and the way to its layout (ADR-0063): to edit it for a
 * worker, to view it for a viewer, who may not change it (ADR-0070).
 */
function CardHeader({ name, sub, layoutTo }: { name: string; sub?: string; layoutTo: string }) {
  const { t } = useI18n();
  const { canWrite } = useSession();
  /* the list's state rides on into the layout, and back */
  const { state: fromList } = useLocation();
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="font-mono text-xl font-semibold text-gray-900">{name}</h1>
        {sub && <div className="mt-1 text-xs text-gray-400">{sub}</div>}
      </div>
      <Link
        to={layoutTo}
        state={fromList}
        className="inline-flex items-center gap-1.5 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:border-gray-500"
      >
        <Folder size={14} className="text-gray-400" /> {t(canWrite ? "gen.card.editLayout" : "gen.card.viewLayout")}
      </Link>
    </div>
  );
}

/**
 * Service card of a service in the /generation list (ADR-0086): the repo, the
 * way to its layout, and what is generated of it. Any other repo - excluded,
 * without endpoints, or unknown - is PageNotFound; the list decides, not the
 * client (ADR-0049). A list that failed to load is a failure with Retry, never
 * PageNotFound (ADR-0081).
 *
 * Its centre follows the stored layout. A service without one gets the one
 * way to make it: "Generate layout" (ADR-0056) - for a worker; a viewer, who
 * may not start it, is told there is none yet (ADR-0070). With one, its
 * resources (`LayoutResources`), each with why it waits on the chosen target,
 * and the way into the layout page for every role. Above it, the choice of
 * target (ADR-0055). The server has no generation data yet, so jobs, coverage
 * and Generate stay switched off (`SHOW_GEN_JOBS`).
 */
export function GenerationServicePage() {
  const { name = "" } = useParams();
  const [searchParams] = useSearchParams();
  /* Opened from the list, the card knows the list's query and search text and leads back to both. */
  const { state: fromList } = useLocation();
  const { t } = useI18n();
  const { canWrite } = useSession();
  const access = useInGeneration(name);
  /* The two targets, Python SDK first as the default (ADR-0055). */
  const targets = useGenerationTargets();
  const targetsBlock = blockOf(targets);
  /* Asked next to the list on the first load, and from then on only for a
     service of the list, as the layout page does (ADR-0078). The card on the
     mock does not read it. Its key holds no target: the layout is the same for
     every one (ADR-0074). */
  const layout = useGenerationLayout(name, { enabled: !SHOW_GEN_JOBS && (access.pending || access.listed) });
  const layoutBlock = blockOf(layout);
  /* A 404 is the backend's word that the service is not in Generation (ADR-0086). */
  const gone = isNotFound(layout.error);
  const start = useStartLayout();
  /* Without `?target=` - or with one no target has - Python SDK is chosen. */
  const chosen = targetsBlock.data && chosenTarget(targetsBlock.data, searchParams.get("target"));

  const listTo = listPath(fromList);
  const back = <ServiceBackLink to={listTo} state={fromList} />;
  const failed = (
    <ServiceLoadFailed
      back={listTo}
      backState={fromList}
      onRetry={() => {
        if (access.failed) access.retry();
        if (layoutBlock.failed && !gone) void retryJoining(layout);
        if (targetsBlock.failed) void retryJoining(targets);
      }}
    />
  );

  if (access.pending) return <ServiceLoading />;
  if (access.failed) return failed;
  if (!access.listed) return <PageNotFound back={back} />;
  if (SHOW_GEN_JOBS) return <TargetCard name={name} back={back} />;
  if (gone) return <PageNotFound back={back} />;
  /* A block that failed shows so even while the other is still on the way. */
  if (layoutBlock.failed || targetsBlock.failed) return failed;
  if (layoutBlock.pending || targetsBlock.pending) return <ServiceLoading />;

  if (!chosen) return <NoTargets back={listTo} backState={fromList} targets={targets} />;
  const { target, defaultTarget } = chosen;

  /* the chosen target rides along into the layout, and back */
  const layoutTo = servicePath(name, target, defaultTarget, ["layout"]);
  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      {back}
      <CardHeader name={name} layoutTo={layoutTo} />
      <TargetSwitcher name={name} targets={targetsBlock.data} target={target} defaultTarget={defaultTarget} />
      {/* The centre of the card, named so it can be found as the place of the resources. */}
      <section
        aria-label={t("gen.card.resources")}
        className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm"
      >
        {layoutBlock.data.has_layout ? (
          /* No "Generate layout" once there is a layout: it changes only by
             editing it (ADR-0072). */
          <LayoutResources layout={layoutBlock.data} target={target} layoutTo={layoutTo} />
        ) : (
          <div className="flex justify-center px-4 py-10">
            {/* The server refuses a viewer the start (ADR-0070): no button - and
                so no spinner or Retry of a start - but a note that there is no layout yet. */}
            {canWrite ? (
              <StartGrouping name={name} start={start} />
            ) : (
              <span className="text-sm text-gray-500">{t("gen.card.noLayoutYet")}</span>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function ToLayout({ layoutTo }: { layoutTo: string }) {
  const { t } = useI18n();
  const { canWrite } = useSession();
  const { state: fromList } = useLocation();
  return (
    <Link
      to={layoutTo}
      state={fromList}
      className="inline-flex items-center gap-1.5 rounded border border-pink-300 bg-pink-50 px-3.5 py-2 text-sm font-semibold text-brand transition hover:border-brand"
    >
      <Folder size={14} /> {t(canWrite ? "gen.card.editLayout" : "gen.card.viewLayout")}
    </Link>
  );
}

/** The centre of a card with a stored layout: the summary while no resource is confirmed (ADR-0062), else the table. */
function LayoutResources({ layout, target, layoutTo }: { layout: Layout; target: GenTarget; layoutTo: string }) {
  const { t } = useI18n();
  const rows = layout.versions.flatMap((v) => v.resources.map((resource) => ({ version: v.api_version, resource })));
  const versions = layout.versions.filter((v) => v.resources.length > 0).length;

  if (rows.length === 0 || rows.every(({ resource }) => resource.confirmed_by == null)) {
    const text =
      rows.length === 0
        ? t("gen.card.empty")
        : t("gen.card.summary", {
            resources: t("gen.card.summary.resources", { n: rows.length }),
            versions: t("gen.card.summary.versions", { n: versions }),
          });
    return (
      <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
        <span className="text-sm text-gray-500">{text}</span>
        <ToLayout layoutTo={layoutTo} />
      </div>
    );
  }

  return (
    <>
      <div className="border-b border-gray-200 bg-gray-50 px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
        {t("gen.card.col.resource")}
      </div>
      {rows.map(({ version, resource }) => (
        <LayoutResourceRow
          key={resource.id}
          version={version}
          resource={resource}
          target={target}
          layoutTo={layoutTo}
        />
      ))}
    </>
  );
}

/**
 * A resource of the stored layout, with why it is held back: first by its
 * layout, then by the chosen target not being connected yet (ADR-0055).
 */
function LayoutResourceRow({
  version,
  resource,
  target,
  layoutTo,
}: {
  version: string;
  resource: LayoutResource;
  target: GenTarget;
  layoutTo: string;
}) {
  const { t } = useI18n();
  const { state: fromList } = useLocation();
  const hold =
    layoutHold(
      resource.confirmed_by != null,
      resource.endpoints.map((e) => e.overall_status),
    ) ?? connectionHold(target);
  const meta = [
    version,
    t("gen.card.endpoints", { n: resource.endpoints.length }),
    resource.confirmed_by != null
      ? t("gen.card.confirmedBy", { by: resource.confirmed_by })
      : t("gen.card.notConfirmed"),
  ].join(" · ");

  return (
    <div
      role="group"
      aria-label={resource.name}
      className="flex flex-wrap items-center gap-3 border-b border-gray-100 px-4 py-[11px] last:border-0"
    >
      <span className="flex min-w-[200px] flex-auto flex-col gap-[3px] overflow-hidden">
        <span className="truncate font-mono text-sm text-gray-800">{resource.name}</span>
        <span className="text-[11px] text-gray-400">{meta}</span>
      </span>
      <HoldReason hold={hold} layoutTo={layoutTo} state={fromList} />
    </div>
  );
}

/**
 * The centre of a service with no layout yet: "Generate layout" and nothing
 * else (ADR-0056); a spinner while the grouping runs (ADR-0060); and if it
 * failed, the failure with Retry in its place (ADR-0061), and for a refusal
 * its reason. A failed start stores nothing, so Retry simply starts it again.
 * The spinner and the failure belong to the service the start was for: a page
 * reused for another one shows that one's button.
 */
function StartGrouping({ name, start }: { name: string; start: ReturnType<typeof useStartLayout> }) {
  const { t } = useI18n();
  const mine = start.variables === name;
  if (mine && start.isPending) return <BlockLoading label={t("gen.card.grouping")} />;
  if (mine && start.isError) {
    /* A refusal says why: a role that may not start it is not a grouping that
       failed, and Retry alone would not tell the two apart. */
    const refused = mutationErrorKey(start.error) === "auth.forbidden";
    const label = t(refused ? "gen.card.groupRefused" : "gen.card.groupFailed");
    return (
      <div className="w-full max-w-md">
        <BlockLoadFailed label={label} onRetry={() => start.mutate(name)} />
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => start.mutate(name)}
      className="inline-flex items-center gap-1.5 rounded border border-pink-300 bg-pink-50 px-3.5 py-2 text-sm font-semibold text-brand transition hover:border-brand"
    >
      <LayoutGrid size={14} /> {t("gen.card.generateLayout")}
    </button>
  );
}

/** How far a target's generation has got: its merged resources out of all. */
interface Coverage {
  merged: number;
  total: number;
}

/**
 * The targets of a service, one of them chosen: Python SDK by default, and
 * Ansible modules, whose generation is not connected yet (ADR-0055). The
 * choice rides in the address as `?target=`, the default left out, and each
 * switch is a step of its own, so Back undoes it - choosing the target already
 * chosen adds no step; the layout is the same for every target, so nothing of
 * it is asked again (ADR-0074).
 *
 * `coverage` is what the card on generation data adds: each target's merged
 * resources, its progress bar and what it waits on. Without it the switcher
 * says only what it knows (`SHOW_GEN_JOBS`).
 */
function TargetSwitcher({
  name,
  targets,
  target,
  defaultTarget,
  coverage,
}: {
  name: string;
  targets: GenTarget[];
  target: GenTarget;
  defaultTarget: GenTarget;
  coverage?: (x: GenTarget) => Coverage;
}) {
  const { t } = useI18n();
  const { state: fromList } = useLocation();
  const navigate = useNavigate();
  /* What a target's card says under its name; null for nothing. */
  const subOf = (x: GenTarget, covered: Coverage | undefined): string | null => {
    if (!covered) return x.live ? null : t("gen.card.notConnected");
    if (!x.live) {
      const base = targets.find((y) => y.id === x.base)?.label;
      return base ? t("gen.waitsOn", { base }) : t("gen.card.planned");
    }
    return covered.total
      ? t("gen.card.merged", { n: covered.merged, total: covered.total })
      : t("gen.card.noResources");
  };
  return (
    /* Named as the choice it is, so its buttons are not read out on their own. */
    <div role="group" aria-label={t("gen.card.targets")} className="mb-2.5 flex flex-wrap gap-2">
      {targets.map((x) => {
        const on = x.id === target.id;
        const covered = coverage?.(x);
        const sub = subOf(x, covered);
        return (
          <button
            type="button"
            key={x.id}
            aria-pressed={on}
            /* A switch is a step of its own; the target already chosen adds none,
               and only tidies an address that names it otherwise. */
            onClick={() => navigate(servicePath(name, x, defaultTarget), { replace: on, state: fromList })}
            className={`min-w-0 flex-1 rounded-lg border px-2.5 py-2 text-left transition ${
              on ? "border-brand bg-pink-50" : "border-gray-200 bg-white hover:border-gray-400"
            }`}
          >
            <span className={`block text-[11px] font-semibold ${on ? "text-brand" : "text-gray-500"}`}>{x.label}</span>
            {sub && (
              <span className={`mt-[3px] block font-mono text-[11px] ${on ? "text-brand" : "text-gray-400"}`}>{sub}</span>
            )}
            {covered && (
              <span className={`mt-1.5 block h-[3px] rounded-sm ${on ? "bg-pink-300" : "bg-gray-100"}`}>
                <span
                  className={`block h-[3px] rounded-sm ${on ? "bg-brand" : "bg-gray-300"}`}
                  style={{ width: `${covered.total ? Math.round((covered.merged / covered.total) * 100) : 0}%` }}
                />
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The card on generation data, one target at a time - coverage of every
 * target, the resources with their state there, and the reason Generate is not
 * offered - or, for a worker, Generate itself (ADR-0070). It reads the
 * in-memory mock, so it is switched off (`SHOW_GEN_JOBS`). The layout is
 * shared by every target and only read here; it is edited on its own page.
 * The target round-trips through the address.
 */
function TargetCard({ name, back }: { name: string; back: ReactNode }) {
  const [searchParams] = useSearchParams();
  const { state: fromList } = useLocation();
  const { t } = useI18n();
  const targets = useGenerationTargets();
  const resources = useGenerationResources(name);
  /* Each block by the one rule (ADR-0081), as on the real page. */
  const targetsBlock = blockOf(targets);
  const resourcesBlock = blockOf(resources);
  const chosen = targetsBlock.data && chosenTarget(targetsBlock.data, searchParams.get("target"));

  const failed = (
    <ServiceLoadFailed
      back={listPath(fromList)}
      backState={fromList}
      onRetry={() => {
        if (targetsBlock.failed) void retryJoining(targets);
        if (resourcesBlock.failed) void retryJoining(resources);
      }}
    />
  );

  if (targetsBlock.failed || resourcesBlock.failed) return failed;
  if (targetsBlock.pending || resourcesBlock.pending) return <ServiceLoading />;

  if (!chosen) return <NoTargets back={listPath(fromList)} backState={fromList} targets={targets} />;
  /* An unknown target falls back to the default, as in the prototype. */
  const { target, defaultTarget } = chosen;
  const labelOf = (id: string | null) => targetsBlock.data.find((x) => x.id === id)?.label;
  const base = labelOf(target.base);

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      {back}

      <CardHeader
        name={name}
        sub={t("gen.card.generating", { target: target.label })}
        layoutTo={servicePath(name, target, defaultTarget, ["layout"])}
      />

      <TargetSwitcher
        name={name}
        targets={targetsBlock.data}
        target={target}
        defaultTarget={defaultTarget}
        coverage={(x) => ({
          merged: resourcesBlock.data.filter((r) => r.jobs[x.id]?.status === "merged").length,
          total: resourcesBlock.data.length,
        })}
      />
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
        {resourcesBlock.data.map((r) => (
          <ResourceRow
            key={r.id}
            resource={r}
            target={target}
            targets={targetsBlock.data}
            pathTo={(rest) => servicePath(name, target, defaultTarget, rest)}
          />
        ))}
        {resourcesBlock.data.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-gray-400">{t("gen.card.empty")}</div>
        )}
      </div>
    </div>
  );
}
