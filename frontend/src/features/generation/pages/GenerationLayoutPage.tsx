import { fieldCls } from "../../../shared/ui/field";
import { linkButtonCls } from "../../../shared/ui/linkButton";
import { ODSButton } from "@telekom-ods/react-ui-kit/ODSButton";
import { useState, type DragEvent } from "react";
import { ODSArrowUTurnBackwards, ODSCheckmark, ODSCircleAdd, ODSClipboard, ODSCollapseDown, ODSDragAndDrop, ODSEdit, ODSFolder, ODSInformation, ODSLock, ODSNavigationExternalLink, ODSNavigationRight, ODSPlay, ODSWarning } from "@telekom-ods/react-icons";
import { Spinner } from "../../../shared/ui/Spinner";
import type { IconComponent } from "../../../shared/ui/icon";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { useGenerationResources, useGenerationServices, useGenerationTargets } from "../data/queries";
import { useEditLayout, useLayoutEdited, type LayoutEdit } from "../data/mutations";
import type { GenJobStatus, GenResource, GenTarget } from "../data/types";
import { LayoutBadge } from "../components/LayoutBadge";
import { PageNotFound } from "../components/PageNotFound";
import { lockingJob, mergedEverywhere } from "../lib/layout";
import { listPath, servicePath } from "../lib/paths";
import {
  RefusalBanner,
  ServiceBackLink,
  ServiceLoadFailed,
  ServiceLoading,
} from "../../scan/components/ServicePageStates";
import { StatusPill } from "../../scan/components/StatusPill";
import { mutationErrorKey } from "../../scan/lib/errors";
import { fmtSnapshotAt } from "../../scan/lib/snapshot";
import { DOC_STATUS_CLS, methodCls } from "../../scan/styles";
import { useSession } from "../../../shared/auth/useSession";
import { useI18n, type MessageKey } from "../../../shared/i18n";

/** A job shown on the layout: one that freezes it, or a failed one that does not. */
type ShownJob = Exclude<GenJobStatus, "merged">;

const JOB_CLS: Record<ShownJob, string> = {
  done: "border-brand-line bg-brand-subtle text-on-brand-subtle",
  running: "border-info-line bg-info-subtle text-info",
  failed: "border-danger-line bg-danger-subtle text-danger",
};

/* a running job shows the ODS spinner instead of an icon */
const JOB_ICON: Record<Exclude<ShownJob, "running">, IconComponent> = { done: ODSLock, failed: ODSWarning };

/** A resource becomes a package of the SDK, so its name has to be a package name - the prototype's rule. */
const PACKAGE_NAME = /^[a-z][a-z0-9_]*$/;

interface Renaming {
  id: string;
  value: string;
  error: string | null;
}

interface Drag {
  endpoint: string;
  from: string;
}

/** Everything a resource row needs from the page: its state there, and the way to change the layout. */
interface RowProps {
  resource: GenResource;
  targets: GenTarget[];
  canWrite: boolean;
  open: boolean;
  onToggle: () => void;
  renaming: Renaming | null;
  setRenaming: (r: Renaming | null) => void;
  saveRename: () => void;
  drag: Drag | null;
  setDrag: (d: Drag | null) => void;
  over: boolean;
  setOver: (id: string | null) => void;
  apply: (edit: LayoutEdit) => void;
}

function ResourceRow({
  resource,
  targets,
  canWrite,
  open,
  onToggle,
  renaming,
  setRenaming,
  saveRename,
  drag,
  setDrag,
  over,
  setOver,
  apply,
}: RowProps) {
  const { t, locale } = useI18n();
  const lock = lockingJob(resource.jobs, targets);
  /* A failed job froze nothing, but it is still shown - the prototype's "failed" pill. */
  const failed = targets.find((x) => resource.jobs[x.id]?.status === "failed");
  const shown: { target: GenTarget; status: ShownJob } | null = lock
    ? { target: lock.target, status: lock.job.status as ShownJob }
    : failed
      ? { target: failed, status: "failed" }
      : null;
  const editable = canWrite && !lock;
  const confirmed = resource.confirmedBy != null;
  const JobIcon = shown && shown.status !== "running" ? JOB_ICON[shown.status] : undefined;

  const dropHere = (e: DragEvent) => {
    if (!drag || !editable) return;
    e.preventDefault();
    if (!over) setOver(resource.id);
  };
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(null);
    setOver(null);
    if (drag && editable && drag.from !== resource.id) apply({ kind: "move", endpoint: drag.endpoint, to: resource.id });
  };

  return (
    <div
      role="group"
      aria-label={resource.name}
      onDragOver={dropHere}
      onDragLeave={() => over && setOver(null)}
      onDrop={drop}
      className={`border-b border-neutral-100 ${over ? "bg-brand-subtle ring-1 ring-inset ring-brand" : ""}`}
    >
      <div className="flex items-center gap-2.5 py-2.5 pl-8 pr-4">
        <button type="button" onClick={onToggle} aria-expanded={open} aria-label={resource.name} className="flex items-center gap-2">
          {open ? <ODSCollapseDown decorative size={13} className="text-neutral-600" /> : <ODSNavigationRight decorative size={13} className="text-neutral-600" />}
          <ODSFolder decorative size={14} className="text-neutral-600" />
        </button>
        {renaming ? (
          <span className="flex flex-auto flex-col gap-1">
            <span className="flex items-center gap-1.5">
              <input
                aria-label={t("gen.layout.rename")}
                value={renaming.value}
                autoFocus
                onChange={(e) => setRenaming({ ...renaming, value: e.target.value, error: null })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveRename();
                  if (e.key === "Escape") setRenaming(null);
                }}
                className={`${fieldCls} w-[220px] font-mono ${renaming.error ? "border-danger hover:border-danger" : ""}`}
              />
              <ODSButton size="small" label={t("gen.layout.save")} onClick={saveRename} />
              <ODSButton size="small" variant="outline" label={t("gen.layout.cancel")} onClick={() => setRenaming(null)} />
            </span>
            {renaming.error && <span className="text-[11px] text-danger">{renaming.error}</span>}
          </span>
        ) : (
          <span className="flex min-w-[200px] flex-auto flex-col gap-0.5 overflow-hidden">
            <span className="truncate font-mono text-sm text-ink">{resource.name}</span>
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-[11px] tabular-nums text-neutral-600">
                {t("gen.card.endpoints", { n: resource.endpoints.length })}
              </span>
              <LayoutBadge resource={resource} />
              {shown && (
                <span
                  title={t(`gen.layout.lock.${shown.status}` as MessageKey, { target: shown.target.label })}
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-px text-[10px] font-semibold uppercase tracking-wide ${JOB_CLS[shown.status]}`}
                >
                  {shown.status === "running" ? <Spinner /> : JobIcon && <JobIcon decorative size={10} />}
                  {t(`gen.job.${shown.status}` as MessageKey)} · {shown.target.label}
                </span>
              )}
              {confirmed && (
                <span className="text-[10px] text-neutral-600">
                  {t("gen.layout.confirmedNote", {
                    by: resource.confirmedBy ?? "",
                    at: fmtSnapshotAt(resource.confirmedAt, locale),
                  })}
                </span>
              )}
            </span>
          </span>
        )}
        {editable && (
          <span className="flex shrink-0 items-center gap-1.5">
            {!confirmed && (
              <ODSButton
                size="small"
                label={t("gen.layout.confirm")}
                buttonIcon={<ODSCheckmark decorative />}
                leftIcon
                onClick={() => apply({ kind: "confirm", resource: resource.id })}
              />
            )}
            <ODSButton
              size="small"
              variant="outline"
              buttonType="iconOnly"
              aria-label={t("gen.layout.rename")}
              title={t("gen.layout.rename")}
              buttonIcon={<ODSEdit decorative />}
              onClick={() => setRenaming({ id: resource.id, value: resource.name, error: null })}
            />
            <ODSButton
              size="small"
              variant="outline"
              buttonType="iconOnly"
              aria-label={t("gen.layout.reset")}
              title={t("gen.layout.reset")}
              buttonIcon={<ODSArrowUTurnBackwards decorative />}
              onClick={() => apply({ kind: "resetResource", resource: resource.id })}
            />
          </span>
        )}
      </div>

      {open && (
        <div className="border-t border-neutral-100 bg-neutral-50">
          {resource.endpoints.map((e) => (
            <div
              key={e.id}
              draggable={editable}
              onDragStart={(ev) => {
                if (!editable) return ev.preventDefault();
                /* Firefox starts no drag without data */
                ev.dataTransfer?.setData("text/plain", e.id);
                setDrag({ endpoint: e.id, from: resource.id });
              }}
              onDragEnd={() => {
                setDrag(null);
                setOver(null);
              }}
              className={`flex items-center gap-2.5 border-t border-neutral-100 py-2 pl-14 pr-4 first:border-t-0 ${
                editable ? "cursor-grab" : ""
              } ${drag?.endpoint === e.id ? "opacity-40" : ""}`}
            >
              <ODSDragAndDrop decorative size={13} className="shrink-0 text-neutral-400" />
              <span
                className={`inline-block w-14 shrink-0 rounded px-1.5 py-0.5 text-center font-mono text-[11px] font-semibold ${methodCls(e.method)}`}
              >
                {e.method}
              </span>
              <span className="w-[230px] shrink-0 truncate font-mono text-xs text-ink-recessive" title={e.uri}>
                {e.uri}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs text-neutral-700" title={e.title}>
                {e.title}
              </span>
              {e.status !== "ok" && (
                <span title={t("gen.layout.notOk")} className={`shrink-0 text-[11px] font-medium ${DOC_STATUS_CLS[e.status]}`}>
                  {t(`docstatus.${e.status}` as MessageKey)}
                </span>
              )}
              <a
                href={e.src}
                target="_blank"
                rel="noreferrer"
                title={t("doc.openSourceHint")}
                className="flex items-center text-neutral-600 transition hover:text-ink-recessive"
              >
                <ODSNavigationExternalLink decorative size={13} />
              </a>
            </div>
          ))}
          {resource.endpoints.length === 0 && (
            <div className="py-3.5 pl-14 pr-4 text-xs text-neutral-600">{t("gen.layout.empty")}</div>
          )}
        </div>
      )}
    </div>
  );
}

const toggled = (set: ReadonlySet<string>, id: string) => {
  const next = new Set(set);
  if (!next.delete(id)) next.add(id);
  return next;
};

/**
 * Layout editor: the versions of a service and the resources the scanner laid
 * out in them, shared by every target. Resources are renamed, filled by dragging
 * endpoints between them, made, confirmed and reset here. One generating or in
 * review on any target is frozen; one merged on every connected target has left
 * for Maintenance and is not shown. The target in the address only rides along
 * to the card and back.
 */
export function GenerationLayoutPage() {
  const { name = "" } = useParams();
  const [searchParams] = useSearchParams();
  /* The list's state, when the card was opened from it: it goes back with the way back. */
  const { state: fromList } = useLocation();
  const { t } = useI18n();
  const { canWrite } = useSession();
  const targets = useGenerationTargets();
  const services = useGenerationServices();
  const resources = useGenerationResources(name);
  const edit = useEditLayout(name);
  /* The prototype's note next to the title: the layout of this service was edited in this session. */
  const edited = useLayoutEdited(name);
  /* Everything starts open, as in the prototype. */
  const [closedVersions, setClosedVersions] = useState<ReadonlySet<string>>(new Set());
  const [closedResources, setClosedResources] = useState<ReadonlySet<string>>(new Set());
  const [renaming, setRenaming] = useState<Renaming | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [over, setOver] = useState<string | null>(null);

  const listTo = listPath(fromList);
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
  if (!services.data.some((s) => s.name === name)) {
    return <PageNotFound back={<ServiceBackLink to={listTo} state={fromList} />} />;
  }
  if (resources.isPending) return loading;
  if (resources.isError) return failed;

  const [defaultTarget] = targets.data;
  const target = targets.data.find((x) => x.id === searchParams.get("target")) ?? defaultTarget;
  const cardTo = servicePath(name, target, defaultTarget);
  const all = resources.data;
  const versions = [...new Set(all.map((r) => r.version))];
  const endpoints = all.reduce((n, r) => n + r.endpoints.length, 0);
  const confirmed = all.filter((r) => r.confirmedBy != null).length;
  const pill = !all.length
    ? { cls: "border-neutral-200 bg-neutral-50 text-neutral-600", label: t("gen.layout.pill.empty") }
    : confirmed === all.length
      ? { cls: "border-success-line bg-success-subtle text-success", label: t("gen.layout.pill.confirmed") }
      : { cls: "border-warning-line bg-warning-subtle text-warning", label: t("gen.layout.pill.unconfirmed") };
  const summary = [
    t("gen.layout.shared"),
    t("gen.layout.versions", { n: versions.length }),
    t("gen.layout.resources", { n: all.length }),
    t("gen.card.endpoints", { n: endpoints }),
    all.length ? t("gen.layout.confirmedOf", { n: confirmed, total: all.length }) : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const apply = (change: LayoutEdit, then?: () => void) => edit.mutate(change, { onSuccess: () => then?.() });
  const saveRename = (resource: GenResource) => {
    if (!renaming) return;
    const value = renaming.value.trim();
    const error = !PACKAGE_NAME.test(value)
      ? t("gen.layout.name.invalid")
      : all.some((r) => r.version === resource.version && r.id !== resource.id && r.name === value)
        ? t("gen.layout.name.taken", { version: resource.version })
        : null;
    if (error) setRenaming({ ...renaming, error });
    else apply({ kind: "rename", resource: resource.id, name: value }, () => setRenaming(null));
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <ServiceBackLink to={cardTo} state={fromList} label={t("gen.layout.back")} />

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="font-mono text-xl font-semibold text-ink">{name}</h1>
            <StatusPill cls={pill.cls} label={pill.label} running={false} />
          </div>
          <div className="mt-1 text-xs text-neutral-600">{summary}</div>
        </div>
        {edited && <span className="text-xs text-neutral-600">{t("gen.layout.edited")}</span>}
      </div>

      {edit.isError && (
        <RefusalBanner
          title={t(mutationErrorKey(edit.error))}
          message={edit.error.message}
          onDismiss={() => edit.reset()}
        />
      )}

      <div className="mb-4 flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs text-neutral-700">
        <ODSInformation decorative size={14} className="shrink-0 text-neutral-600" /> {t("gen.layout.info")}
      </div>

      {versions.map((version) => {
        const open = !closedVersions.has(version);
        const inVersion = all.filter((r) => r.version === version);
        const shown = inVersion.filter((r) => !mergedEverywhere(r.jobs, targets.data));
        const moved = inVersion.length - shown.length;
        return (
          <section
            key={version}
            aria-label={version}
            className="mb-4 overflow-hidden rounded-xl border border-neutral-200 bg-surface shadow-sm"
          >
            <div className="flex items-center gap-2.5 border-b border-neutral-200 bg-neutral-50 px-4 py-2.5">
              <button
                type="button"
                aria-expanded={open}
                onClick={() => setClosedVersions(toggled(closedVersions, version))}
                className="flex items-center gap-2"
              >
                {open ? <ODSCollapseDown decorative size={14} className="text-neutral-700" /> : <ODSNavigationRight decorative size={14} className="text-neutral-700" />}
                <span className="font-mono text-sm font-semibold text-ink">{version}</span>
              </button>
              <span className="font-mono text-xs tabular-nums text-neutral-600">
                {t("gen.layout.resources", { n: shown.length })} ·{" "}
                {t("gen.card.endpoints", { n: shown.reduce((n, r) => n + r.endpoints.length, 0) })}
              </span>
              {moved > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full border border-brand-line bg-brand-subtle px-2 py-px text-[10px] font-semibold text-on-brand-subtle">
                  <ODSClipboard decorative size={12} /> {t("gen.layout.moved", { n: moved })}
                </span>
              )}
              {canWrite && (
                <span className="ml-auto flex items-center gap-2">
                  <ODSButton
                    size="small"
                    variant="outline"
                    label={t("gen.layout.newResource")}
                    buttonIcon={<ODSCircleAdd decorative />}
                    leftIcon
                    onClick={() => apply({ kind: "add", version })}
                  />
                  <ODSButton
                    size="small"
                    variant="outline"
                    label={t("gen.layout.reset")}
                    buttonIcon={<ODSArrowUTurnBackwards decorative />}
                    leftIcon
                    onClick={() => apply({ kind: "resetVersion", version })}
                  />
                </span>
              )}
            </div>
            {open && (
              <div>
                <div className="border-b border-neutral-100 bg-neutral-50/50 py-1.5 pl-8 pr-4 text-[10px] font-semibold uppercase tracking-wide text-neutral-600">
                  {t("gen.layout.col")}
                </div>
                {shown.map((r) => (
                  <ResourceRow
                    key={r.id}
                    resource={r}
                    targets={targets.data}
                    canWrite={canWrite}
                    open={!closedResources.has(r.id)}
                    onToggle={() => setClosedResources(toggled(closedResources, r.id))}
                    renaming={renaming?.id === r.id ? renaming : null}
                    setRenaming={setRenaming}
                    saveRename={() => saveRename(r)}
                    drag={drag}
                    setDrag={setDrag}
                    over={over === r.id}
                    setOver={setOver}
                    apply={apply}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}

      {versions.length === 0 && (
        <div className="mb-4 rounded-xl border border-dashed border-neutral-200 bg-neutral-50 px-6 py-14 text-center text-sm text-neutral-600">
          {t("gen.layout.nothing")}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-neutral-200 bg-surface px-3.5 py-3 text-xs text-neutral-700">
        {t("gen.layout.footer")}
        <Link
          to={cardTo}
          state={fromList}
          className={`ml-auto ${linkButtonCls}`}
        >
          <ODSPlay decorative size={16} /> {t("gen.layout.back")}
        </Link>
      </div>
    </div>
  );
}
