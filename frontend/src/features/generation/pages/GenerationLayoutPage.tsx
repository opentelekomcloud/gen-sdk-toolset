import { useId, useState, type DragEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Folder,
  FolderPlus,
  GripVertical,
  Info,
  Loader2,
  Lock,
  Pencil,
  Play,
  type LucideIcon,
} from "lucide-react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { useGenerationLayout, useGenerationResources, useGenerationTargets, useInGeneration } from "../data/queries";
import { useEditLayout, useLayoutEdited, useLayoutEditing, type LayoutEdit } from "../data/mutations";
import type { GenJobStatus, GenOrigin, GenResource, GenTarget } from "../data/types";
import { LayoutBadge } from "../components/LayoutBadge";
import { PageNotFound } from "../components/PageNotFound";
import { confirmBlock, lockingJob, mergedEverywhere, movable, nameProblem, type EndpointSource } from "../lib/layout";
import { chosenTarget, generationPath, listPath, servicePath } from "../lib/paths";
import { SHOW_GEN_JOBS, SHOW_LAYOUT_ORIGIN } from "../flags";
import {
  BlockFailed,
  NoticeBanner,
  RefusalBanner,
  ServiceBackLink,
  ServiceLoadFailed,
  ServiceLoading,
} from "../../scan/components/ServicePageStates";
import { StatusPill } from "../../scan/components/StatusPill";
import { isNotFound } from "../../scan/api/client";
import { blockOf, retryJoining, type Retryable } from "../../scan/api/queries";
import { mutationErrorKey } from "../../scan/lib/errors";
import { fmtSnapshotAt } from "../../scan/lib/snapshot";
import { DOC_STATUS_CLS, methodCls } from "../../scan/styles";
import type { DocStatus } from "../../scan/types";
import type { DocumentListItem, Layout, LayoutResource } from "../../../shared/api/types";
import { useSession } from "../../../shared/auth/useSession";
import { useI18n, type MessageKey } from "../../../shared/i18n";

/** A job shown on the layout: one that freezes it, or a failed one that does not. */
type ShownJob = Exclude<GenJobStatus, "merged">;

const JOB_CLS: Record<ShownJob, string> = {
  done: "border-violet-200 bg-violet-50 text-violet-700",
  running: "border-blue-200 bg-blue-50 text-blue-700",
  failed: "border-red-200 bg-red-50 text-red-700",
};

const JOB_ICON: Record<ShownJob, LucideIcon> = { done: Lock, running: Loader2, failed: AlertTriangle };

/**
 * A name being typed: a new one for the resource `resource`, or, with `null`
 * there, the name of a resource to add to `version`. One at a time: no other
 * field opens before it is saved or dropped.
 *
 * It is an unsaved edit, so the page holds what it shows as it was when the
 * name was asked - the `layout`, and the `targets` and `resources` the flags
 * show of generation - and nothing changes it under the name (ADR-0083): no
 * refresh, and no other edit of the user's, since none starts while a name is
 * typed.
 */
interface Naming {
  layout: Layout;
  targets: GenTarget[] | undefined;
  resources: GenResource[] | undefined;
  resource: number | null;
  version: string;
  value: string;
  error: string | null;
}

/** An endpoint being dragged, by its document `path`, and where it comes from. */
interface Drag {
  path: string;
  from: EndpointSource;
}

/**
 * The page's drag and drop: what is dragged, the resource it is over, and the
 * move a drop makes. Nothing is dragged, and no name field opens, while the
 * page is `busy` - an edit under way, or a name being typed: one edit at a
 * time, so that answers cannot arrive out of order, nor change the layout
 * under an unsaved name, nor a name be dropped by opening another.
 */
interface Dragging {
  busy: boolean;
  drag: Drag | null;
  setDrag: (d: Drag | null) => void;
  over: number | null;
  setOver: (id: number | null) => void;
  move: (path: string, to: number) => void;
}

/**
 * What a resource shows of generation, which the stored layout does not hold:
 * its jobs on every target (`SHOW_GEN_JOBS`) and where it came from
 * (`SHOW_LAYOUT_ORIGIN`). Each is null while its flag is off.
 * TODO(#150): read from the server with real generation data.
 */
interface Generated {
  jobs: GenResource["jobs"] | null;
  origin: GenOrigin | null;
}

/**
 * The name field of a rename or of a resource being added: Enter or Save takes
 * it, Escape or Cancel drops it. While its save is under way it takes no more
 * typing: the answer closes it, and what was typed since would be lost.
 */
function NameField({
  label,
  naming,
  setNaming,
  save,
  saveOff,
  saving,
}: {
  label: string;
  naming: Naming;
  setNaming: (n: Naming | null) => void;
  save: () => void;
  /** No save now: one is under way, or the service has left (ADR-0082). */
  saveOff: boolean;
  /** An edit is under way. */
  saving: boolean;
}) {
  const { t } = useI18n();
  return (
    <span className="flex flex-auto flex-col gap-1">
      <span className="flex items-center gap-1.5">
        <input
          aria-label={label}
          value={naming.value}
          readOnly={saving}
          autoFocus
          onChange={(e) => setNaming({ ...naming, value: e.target.value, error: null })}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !saveOff) save();
            if (e.key === "Escape") setNaming(null);
          }}
          className={`w-[200px] rounded border bg-white px-2 py-1 font-mono text-[13px] text-gray-800 outline-none ${
            naming.error ? "border-red-300" : "border-gray-300"
          }`}
        />
        <button
          type="button"
          onClick={save}
          disabled={saveOff}
          className="rounded bg-brand px-2.5 py-1 text-xs font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
        >
          {t("gen.layout.save")}
        </button>
        <button
          type="button"
          onClick={() => setNaming(null)}
          className="rounded border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500"
        >
          {t("gen.layout.cancel")}
        </button>
      </span>
      {naming.error && <span className="text-[11px] text-red-700">{naming.error}</span>}
    </span>
  );
}

/** A document status the panel has words for; the backend may send one it does not know yet. */
const knownStatus = (status: string): status is DocStatus => Object.hasOwn(DOC_STATUS_CLS, status);

/** One endpoint, by its document: dragged by its row where it may be moved. */
function EndpointRow({
  endpoint,
  from,
  draggable,
  dragging,
}: {
  endpoint: DocumentListItem;
  from: EndpointSource;
  draggable: boolean;
  dragging: Dragging;
}) {
  const { t } = useI18n();
  const { drag, setDrag, setOver } = dragging;
  const status = endpoint.overall_status;
  return (
    <div
      draggable={draggable}
      onDragStart={(ev) => {
        if (!draggable) return ev.preventDefault();
        /* Firefox starts no drag without data */
        ev.dataTransfer?.setData("text/plain", endpoint.path);
        setDrag({ path: endpoint.path, from });
      }}
      onDragEnd={() => {
        setDrag(null);
        setOver(null);
      }}
      className={`flex items-center gap-2.5 border-t border-gray-100 py-2 pl-14 pr-4 first:border-t-0 ${
        draggable ? "cursor-grab" : ""
      } ${drag?.path === endpoint.path ? "opacity-40" : ""}`}
    >
      <GripVertical size={13} className="shrink-0 text-gray-300" />
      <span
        className={`inline-block w-14 shrink-0 rounded px-1.5 py-0.5 text-center font-mono text-[11px] font-semibold ${methodCls(endpoint.method ?? "")}`}
      >
        {endpoint.method ?? "—"}
      </span>
      <span className="w-[230px] shrink-0 truncate font-mono text-xs text-gray-600" title={endpoint.uri ?? undefined}>
        {endpoint.uri ?? "—"}
      </span>
      {/* The endpoint is its document: its title, or its path where it has none. */}
      <span className="min-w-0 flex-1 truncate text-xs text-gray-500" title={endpoint.path}>
        {endpoint.title || endpoint.path}
      </span>
      {status !== "ok" && (
        <span
          title={t("gen.layout.notOk")}
          className={`shrink-0 text-[11px] font-medium ${knownStatus(status) ? DOC_STATUS_CLS[status] : ""}`}
        >
          {/* One the panel does not know is shown as the backend sends it. */}
          {knownStatus(status) ? t(`docstatus.${status}`) : status}
        </span>
      )}
    </div>
  );
}

/** Everything a resource row needs from the page: its state there, and the way to change the layout. */
interface RowProps {
  resource: LayoutResource;
  version: string;
  generated: Generated;
  targets: GenTarget[];
  canWrite: boolean;
  open: boolean;
  onToggle: () => void;
  naming: Naming | null;
  setNaming: (n: Naming | null) => void;
  onRename: () => void;
  onConfirm: () => void;
  saveName: () => void;
  saveOff: boolean;
  saving: boolean;
  dragging: Dragging;
}

function ResourceRow({
  resource,
  version,
  generated,
  targets,
  canWrite,
  open,
  onToggle,
  naming,
  setNaming,
  onRename,
  onConfirm,
  saveName,
  saveOff,
  saving,
  dragging,
}: RowProps) {
  const { t, locale } = useI18n();
  const hintId = useId();
  const { drag, setDrag, over, setOver, move } = dragging;
  const { jobs, origin } = generated;
  const lock = jobs && lockingJob(jobs, targets);
  /* A failed job froze nothing, but it is still shown - the prototype's "failed" pill. */
  const failed = jobs && targets.find((x) => jobs[x.id]?.status === "failed");
  const shown: { target: GenTarget; status: ShownJob } | null = lock
    ? { target: lock.target, status: lock.job.status as ShownJob }
    : failed
      ? { target: failed, status: "failed" }
      : null;
  const editable = canWrite && !lock;
  const confirmed = resource.confirmed_by != null;
  /* Why it cannot be confirmed, if it cannot (ADR-0067): its own endpoints
     only, so nothing here blocks another resource. */
  const block = confirmed ? null : confirmBlock(resource.endpoints);
  const JobIcon = shown && JOB_ICON[shown.status];
  const accepts = drag != null && editable && movable(drag.from, { id: resource.id, version });
  const isOver = over === resource.id;

  const dropHere = (e: DragEvent) => {
    if (!accepts) return;
    e.preventDefault();
    if (!isOver) setOver(resource.id);
  };
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(null);
    setOver(null);
    if (drag && accepts) move(drag.path, resource.id);
  };

  return (
    <div
      role="group"
      aria-label={resource.name}
      onDragOver={dropHere}
      onDragLeave={() => isOver && setOver(null)}
      onDrop={drop}
      className={`border-b border-gray-100 ${isOver ? "bg-pink-50 ring-1 ring-inset ring-brand" : ""}`}
    >
      <div className="flex items-center gap-2.5 py-2.5 pl-8 pr-4">
        <button type="button" onClick={onToggle} aria-expanded={open} aria-label={resource.name} className="flex items-center gap-2">
          {open ? <ChevronDown size={13} className="text-gray-400" /> : <ChevronRight size={13} className="text-gray-400" />}
          <Folder size={14} className="text-gray-400" />
        </button>
        {naming ? (
          <NameField
            label={t("gen.layout.rename")}
            naming={naming}
            setNaming={setNaming}
            save={saveName}
            saveOff={saveOff}
            saving={saving}
          />
        ) : (
          <span className="flex min-w-[200px] flex-auto flex-col gap-0.5 overflow-hidden">
            <span className="truncate font-mono text-sm text-gray-800">{resource.name}</span>
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-[11px] tabular-nums text-gray-400">
                {t("gen.card.endpoints", { n: resource.endpoints.length })}
              </span>
              <LayoutBadge confirmed={confirmed} origin={origin} />
              {shown && JobIcon && (
                <span
                  title={t(`gen.layout.lock.${shown.status}` as MessageKey, { target: shown.target.label })}
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-px text-[10px] font-semibold uppercase tracking-wide ${JOB_CLS[shown.status]}`}
                >
                  <JobIcon size={10} className={shown.status === "running" ? "animate-spin" : undefined} />
                  {t(`gen.job.${shown.status}` as MessageKey)} · {shown.target.label}
                </span>
              )}
              <span className="text-[10px] text-gray-400">
                {confirmed
                  ? t("gen.layout.confirmedNote", {
                      by: resource.confirmed_by ?? "",
                      at: fmtSnapshotAt(resource.confirmed_at, locale),
                    })
                  : t("gen.card.notConfirmed")}
              </span>
            </span>
          </span>
        )}
        {/* Each resource on its own (ADR-0066): there is no Confirm for a version or the whole layout. */}
        {editable && !confirmed && !naming && (
          <span className="flex shrink-0 items-center gap-1.5">
            {block && (
              <span id={hintId} className="text-[11px] text-amber-700">
                {block.reason === "empty"
                  ? t("gen.layout.confirm.empty")
                  : t("gen.layout.confirm.notOk", { n: block.notOk })}
              </span>
            )}
            <button
              type="button"
              onClick={onConfirm}
              disabled={dragging.busy || block !== null}
              aria-describedby={block ? hintId : undefined}
              className="inline-flex items-center gap-1.5 rounded border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 transition hover:border-emerald-400 disabled:opacity-50"
            >
              <Check size={12} /> {t("gen.layout.confirm")}
            </button>
          </span>
        )}
        {editable && !naming && (
          <button
            type="button"
            title={t("gen.layout.rename")}
            aria-label={t("gen.layout.rename")}
            onClick={onRename}
            disabled={dragging.busy}
            className="inline-flex shrink-0 items-center rounded border border-gray-300 bg-white px-1.5 py-1 transition hover:border-gray-500 disabled:opacity-50"
          >
            <Pencil size={12} className="text-gray-500" />
          </button>
        )}
      </div>

      {open && (
        <div className="border-t border-gray-100 bg-gray-50">
          {resource.endpoints.map((e) => (
            <EndpointRow
              key={e.path}
              endpoint={e}
              from={{ resource: resource.id, version }}
              draggable={editable && !dragging.busy}
              dragging={dragging}
            />
          ))}
          {resource.endpoints.length === 0 && (
            <div className="py-3.5 pl-14 pr-4 text-xs text-gray-400">{t("gen.layout.empty")}</div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Endpoints in no resource: the "unassigned" list of a version, or the "no
 * version" list. Their endpoints are dragged into a resource from here, and
 * nothing is dropped back: a list is no target (ADR-0064).
 */
function EndpointList({
  label,
  hint,
  endpoints,
  version,
  canWrite,
  dragging,
}: {
  label: string;
  hint: string;
  endpoints: DocumentListItem[];
  version: string | null;
  canWrite: boolean;
  dragging: Dragging;
}) {
  const { t } = useI18n();
  return (
    <div role="group" aria-label={label} className="border-b border-gray-100 last:border-0">
      <div className="flex flex-wrap items-center gap-2.5 py-2.5 pl-8 pr-4">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        <span className="font-mono text-[11px] tabular-nums text-gray-400">{t("gen.card.endpoints", { n: endpoints.length })}</span>
        <span className="text-[11px] text-gray-400">{hint}</span>
      </div>
      <div className="border-t border-gray-100 bg-gray-50">
        {endpoints.map((e) => (
          <EndpointRow
            key={e.path}
            endpoint={e}
            from={{ resource: null, version }}
            draggable={canWrite && !dragging.busy}
            dragging={dragging}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * The top of the layout page: the way back to the service page, the repo with
 * the state of its layout, and what the editor adds - its summary and the note
 * that changes were saved on the service.
 */
function LayoutHeader({
  name,
  cardTo,
  pill,
  summary,
  aside,
}: {
  name: string;
  cardTo: string;
  pill: { cls: string; label: string } | null;
  summary?: string;
  aside?: ReactNode;
}) {
  const { t } = useI18n();
  const { state: fromList } = useLocation();
  return (
    <>
      <ServiceBackLink to={cardTo} state={fromList} label={t("gen.layout.back")} />
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="font-mono text-xl font-semibold text-gray-900">{name}</h1>
            {pill && <StatusPill cls={pill.cls} label={pill.label} running={false} />}
          </div>
          {summary && <div className="mt-1 text-xs text-gray-400">{summary}</div>}
        </div>
        {aside}
      </div>
    </>
  );
}

/**
 * The page with nothing to edit: the title, a note where the editor would be,
 * and the way to the service page - a page of its own, not a redirect
 * (ADR-0086).
 */
function NothingToEdit({ name, cardTo, note }: { name: string; cardTo: string; note: string }) {
  const { t } = useI18n();
  /* The list's state, when the card was opened from it: it goes back with the way back. */
  const { state: fromList } = useLocation();
  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <LayoutHeader
        name={name}
        cardTo={cardTo}
        pill={{ cls: "border-gray-200 bg-gray-50 text-gray-400", label: t("gen.layout.pill.noLayout") }}
      />
      <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-6 py-14 text-center text-sm text-gray-400">
        {note}
        <Link
          to={cardTo}
          state={fromList}
          className="mx-auto mt-3 flex w-fit items-center gap-1.5 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:border-gray-500"
        >
          <Play size={12} /> {t("gen.layout.toCard")}
        </Link>
      </div>
    </div>
  );
}

const toggled = <T,>(set: ReadonlySet<T>, id: T) => {
  const next = new Set(set);
  if (!next.delete(id)) next.add(id);
  return next;
};

/**
 * Layout editor: the stored layout of a service, shared by every target - each
 * version with its resources and their endpoints, the endpoints of the version
 * in no resource ("unassigned"), and the endpoints with no version at all. Here
 * a resource is renamed, one is added - its name asked for as a rename asks -
 * an endpoint is dragged into a resource where the move is allowed (ADR-0064),
 * and a resource is confirmed on its own, once its endpoints allow it
 * (ADR-0066, ADR-0067). Each edit is the server's: the page shows the layout
 * it answers with, and a refusal in a banner. Nothing deletes a resource or
 * resets the layout. The target in the address only rides along to the card
 * and back.
 *
 * It opens for a service in the /generation list (ADR-0086). Whether the
 * service has a layout is the backend's answer (`has_layout`); without one the
 * page is an empty state that leads to the service page, not a redirect.
 */
export function GenerationLayoutPage() {
  const { name = "" } = useParams();
  /* Keyed by the service: a page reused for another one starts afresh, with
     nothing of the last one's - a name typed there above all. */
  return <LayoutEditor key={name} name={name} />;
}

function LayoutEditor({ name }: { name: string }) {
  const [searchParams] = useSearchParams();
  /* The list's state, when the card was opened from it: it goes back with the way back. */
  const { state: fromList } = useLocation();
  const { t } = useI18n();
  const { canWrite } = useSession();
  const targets = useGenerationTargets();
  const targetsBlock = blockOf(targets);
  const access = useInGeneration(name);
  /* Asked next to the list on the first load, and from then on only for a
     service of the list: the backend answers 404 for any other, and a page not
     shown is not asked for (ADR-0078). */
  const layout = useGenerationLayout(name, { enabled: access.pending || access.listed });
  const layoutBlock = blockOf(layout);
  /* What the stored layout does not hold - a resource's jobs and where it came
     from - read from the mock, by version and name, while a flag shows it. */
  const fromMock = SHOW_GEN_JOBS || SHOW_LAYOUT_ORIGIN;
  const resources = useGenerationResources(name, { enabled: fromMock && layout.data?.has_layout === true });
  const resourcesBlock = blockOf(resources);
  const edit = useEditLayout(name);
  /* An edit of this service under way, this page's or one a page left since sent. */
  const editing = useLayoutEditing(name);
  /* The prototype's note next to the title: changes to this service's layout - an edit or a confirmation - were saved in this session. */
  const edited = useLayoutEdited(name);
  /* Everything starts open, as in the prototype. */
  const [closedVersions, setClosedVersions] = useState<ReadonlySet<string>>(new Set());
  const [closedResources, setClosedResources] = useState<ReadonlySet<number>>(new Set());
  const [naming, setNaming] = useState<Naming | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [over, setOver] = useState<number | null>(null);

  /* The way back to the card; the target the address names rides along
     (ADR-0063), chosen as the card chooses it - the default and one there is
     not are left off. Until the targets are read - or while they failed, whose
     last answer is not current (ADR-0081) - it rides along as it is. */
  const asked = searchParams.get("target");
  const chosen = targetsBlock.data && chosenTarget(targetsBlock.data, asked);
  const cardTo = chosen ? servicePath(name, chosen.target, chosen.defaultTarget) : generationPath(name, [], asked);
  /* A 404 is the backend's word that the service is not in Generation, not a
     failure: the page turns into the one a direct address shows (ADR-0086) -
     with a name being typed, only once it is dropped (ADR-0082). */
  const gone = isNotFound(layout.error);
  const listTo = listPath(fromList);
  const loading = <ServiceLoading />;
  const failed = (
    <ServiceLoadFailed
      back={listTo}
      backState={fromList}
      onRetry={() => {
        if (access.failed) access.retry();
        if (layoutBlock.failed && !gone) void retryJoining(layout);
        if (targetsBlock.failed) void retryJoining(targets);
        if (resourcesBlock.failed) void retryJoining(resources);
      }}
    />
  );

  /* The service has left Generation: the backend's 404 for its layout - an
     answer, which wins over a list that failed to refresh in the same round -
     or a list that no longer holds it. */
  const vanished = gone || (!access.failed && !access.listed);
  /* A name being typed is an unsaved edit, and the page under it stays the one
     it was asked on: a failed refresh of the list, of the layout or of what the
     flags show of generation leaves it with a warning (ADR-0081), and any of
     them read since that differs - or a service that has left - with "Data
     changed", whose Refresh drops the name and shows the page as it is now
     (ADR-0083, ADR-0082). The cache shares what did not change, so a read that
     changed nothing is the very data the name was asked on. The answer of the user's own save is no one else's
     change, and closes the name once it is in. */
  const refreshes: [failed: boolean, query: Retryable][] = [
    [access.failed, access.query],
    [layoutBlock.failed, layout],
    [SHOW_GEN_JOBS && targetsBlock.failed, targets],
    [fromMock && resourcesBlock.failed, resources],
  ];
  const failedRefresh = gone ? null : (refreshes.find(([failed]) => failed)?.[1] ?? null);
  const keepEdit = failedRefresh !== null && naming !== null;
  const changed =
    naming !== null &&
    !editing &&
    (vanished ||
      naming.layout !== layout.data ||
      (SHOW_GEN_JOBS && naming.targets !== targets.data) ||
      (fromMock && naming.resources !== resources.data));
  const notFound = <PageNotFound back={<ServiceBackLink to={listTo} state={fromList} />} />;
  if (access.pending) return loading;
  if (!naming) {
    if (vanished) return notFound;
    if (access.failed || layoutBlock.failed) return failed;
    if (layoutBlock.pending) return loading;
  }
  const stored = naming ? naming.layout : layoutBlock.data;
  if (!stored) return loading;

  /* No layout until the preliminary grouping has run: an empty state that
     leads to the service page, not a redirect (ADR-0086). */
  if (!stored.has_layout) return <NothingToEdit name={name} cardTo={cardTo} note={t("gen.layout.noLayout")} />;
  /* The layout itself needs no target - it is the same for every one
     (ADR-0074) - so with none, or with targets that failed, it still opens.
     Only what the flags show of generation needs them, and the mock's
     resources: which job freezes a resource, which merged one has left. */
  if (!naming) {
    if ((SHOW_GEN_JOBS && targetsBlock.failed) || (fromMock && resourcesBlock.failed)) return failed;
    if ((SHOW_GEN_JOBS && targetsBlock.pending) || (fromMock && resourcesBlock.pending)) return loading;
  }
  const shownTargets = SHOW_GEN_JOBS ? ((naming ? naming.targets : targetsBlock.data) ?? []) : [];
  const mocked = naming ? naming.resources : resourcesBlock.data;
  const generatedOf = (version: string, resource: string): Generated => {
    const mock = mocked?.find((r) => r.version === version && r.name === resource);
    return { jobs: SHOW_GEN_JOBS ? (mock?.jobs ?? {}) : null, origin: SHOW_LAYOUT_ORIGIN ? (mock?.origin ?? null) : null };
  };
  const hidden = (version: string, r: LayoutResource) => {
    const { jobs } = generatedOf(version, r.name);
    return jobs != null && mergedEverywhere(jobs, shownTargets);
  };

  /* The header counts what the page shows, as the header of each version does:
     a resource it leaves out - merged on every connected target, moved on - is
     counted nowhere, the pill included. */
  const all = stored.versions.flatMap((v) => v.resources.filter((r) => !hidden(v.api_version, r)));
  const movedOn = stored.versions.reduce((n, v) => n + v.resources.length, 0) - all.length;
  const endpoints =
    all.reduce((n, r) => n + r.endpoints.length, 0) +
    stored.versions.reduce((n, v) => n + v.unassigned.length, 0) +
    stored.no_version.length;
  const confirmed = all.filter((r) => r.confirmed_by != null).length;
  /* Confirmed when every resource shown is; with none shown, only when some
     have moved on - then nothing is left to confirm. A layout of no resources
     at all is still to be laid out. */
  const layoutConfirmed = all.length > 0 ? confirmed === all.length : movedOn > 0;
  const pill = layoutConfirmed
    ? { cls: "border-emerald-200 bg-emerald-50 text-emerald-700", label: t("gen.layout.pill.confirmed") }
    : { cls: "border-amber-200 bg-amber-50 text-amber-800", label: t("gen.layout.pill.unconfirmed") };
  const summary = [
    t("gen.layout.shared"),
    t("gen.layout.versions", { n: stored.versions.length }),
    t("gen.layout.resources", { n: all.length }),
    t("gen.card.endpoints", { n: endpoints }),
    /* "0 of 0" says nothing: with no resource shown it is left out. */
    ...(all.length > 0 ? [t("gen.layout.confirmedOf", { n: confirmed, total: all.length })] : []),
  ].join(" · ");

  /* One edit at a time (see `useEditLayout`): while one is under way nothing
     is dragged, no name is saved and no name field opens; while a name is typed
     nothing is dragged. So the only answer that can come in under a name is its
     own save's, which closes it; a refused one leaves it open. */
  const saveOff = editing || vanished;
  const apply = (change: LayoutEdit) =>
    edit.mutate({ repo: name, edit: change }, { onSuccess: () => setNaming(null) });
  /* A name is asked on the layout as it is shown. */
  const ask = (resource: number | null, version: string, value: string) =>
    setNaming({
      layout: stored,
      targets: targetsBlock.data,
      resources: resourcesBlock.data,
      resource,
      version,
      value,
      error: null,
    });
  /* Refresh in "Data changed": the name goes, and the layout - the one thing
     here read from the server - is read again, joining a read already asking
     (ADR-0084), unless the service has left, which is all there is to show. */
  const dropName = () => {
    setNaming(null);
    if (!vanished) void retryJoining(layout);
  };
  const dragging: Dragging = {
    busy: editing || naming !== null,
    drag,
    setDrag,
    over,
    setOver,
    move: (path, to) => apply({ kind: "move", path, to }),
  };
  /* A name is checked here before it goes out (ADR-0065): a package name, and
     free in its version - every resource of it counts, a hidden one too. The
     server checks both again, and says so in a banner. */
  const saveName = () => {
    if (!naming) return;
    const value = naming.value.trim();
    const inVersion = stored.versions.find((v) => v.api_version === naming.version)?.resources ?? [];
    const current = inVersion.find((r) => r.id === naming.resource);
    if (current?.name === value) return setNaming(null);
    const taken = inVersion.filter((r) => r.id !== naming.resource).map((r) => r.name);
    const problem = nameProblem(value, taken);
    if (problem) {
      const error =
        problem === "invalid" ? t("gen.layout.name.invalid") : t("gen.layout.name.taken", { version: naming.version });
      return setNaming({ ...naming, error });
    }
    const change: LayoutEdit =
      naming.resource === null
        ? { kind: "add", version: naming.version, name: value }
        : { kind: "rename", resource: naming.resource, name: value };
    apply(change);
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <LayoutHeader
        name={name}
        cardTo={cardTo}
        pill={pill}
        summary={summary}
        aside={edited && <span className="text-xs text-gray-400">{t("gen.layout.edited")}</span>}
      />

      {keepEdit && (
        <div className="mb-4">
          <BlockFailed query={failedRefresh} label={t("gen.layout.refreshFailed")} loadingLabel={t("service.loading")} />
        </div>
      )}

      {changed && (
        <NoticeBanner title={t("gen.layout.changed")} action={t("gen.layout.changed.refresh")} onAction={dropName}>
          {t("gen.layout.changed.hint")}
        </NoticeBanner>
      )}

      {edit.isError && (
        <RefusalBanner
          title={t(mutationErrorKey(edit.error))}
          message={edit.error.message}
          onDismiss={() => edit.reset()}
        />
      )}

      <div className="mb-4 flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-500">
        <Info size={14} className="shrink-0 text-gray-400" /> {t("gen.layout.info")}
      </div>

      {stored.versions.length === 0 && stored.no_version.length === 0 && (
        <div className="mb-4 rounded-xl border border-dashed border-gray-200 bg-gray-50 px-6 py-10 text-center text-sm text-gray-400">
          {t("gen.card.empty")}
        </div>
      )}

      {stored.versions.map(({ api_version: version, resources: inVersion, unassigned }) => {
        /* A version holding the name being typed stays open, its fold shut off:
           folded, it would hide the field - its Save and Cancel - while the
           name still holds the rest of the page (ADR-0083). Once the name is
           saved or dropped, the version is as it was. */
        const holdsName = naming?.version === version;
        const open = holdsName || !closedVersions.has(version);
        const shown = inVersion.filter((r) => !hidden(version, r));
        const moved = inVersion.length - shown.length;
        const adding = naming?.resource === null && naming.version === version ? naming : null;
        return (
          <section
            key={version}
            aria-label={version}
            className="mb-4 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm"
          >
            <div className="flex items-center gap-2.5 border-b border-gray-200 bg-gray-50 px-4 py-2.5">
              <button
                type="button"
                aria-expanded={open}
                onClick={() => setClosedVersions(toggled(closedVersions, version))}
                disabled={holdsName}
                className="flex items-center gap-2"
              >
                {open ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
                <span className="font-mono text-sm font-semibold text-gray-900">{version}</span>
              </button>
              <span className="font-mono text-xs tabular-nums text-gray-400">
                {t("gen.layout.resources", { n: shown.length })} ·{" "}
                {t("gen.card.endpoints", {
                  n: shown.reduce((n, r) => n + r.endpoints.length, 0) + unassigned.length,
                })}
              </span>
              {moved > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full border border-violet-200 bg-violet-50 px-2 py-px text-[10px] font-semibold text-violet-700">
                  <ClipboardCheck size={12} /> {t("gen.layout.moved", { n: moved })}
                </span>
              )}
              {canWrite && !adding && (
                <button
                  type="button"
                  onClick={() => ask(null, version, "")}
                  disabled={dragging.busy}
                  className="ml-auto inline-flex items-center gap-1.5 rounded border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500 disabled:opacity-50"
                >
                  <FolderPlus size={12} /> {t("gen.layout.newResource")}
                </button>
              )}
            </div>
            {open && (
              <div>
                <div className="border-b border-gray-100 bg-gray-50/50 py-1.5 pl-8 pr-4 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                  {t("gen.layout.col")}
                </div>
                {shown.map((r) => (
                  <ResourceRow
                    key={r.id}
                    resource={r}
                    version={version}
                    generated={generatedOf(version, r.name)}
                    targets={shownTargets}
                    canWrite={canWrite}
                    open={!closedResources.has(r.id)}
                    onToggle={() => setClosedResources(toggled(closedResources, r.id))}
                    naming={naming?.resource === r.id ? naming : null}
                    setNaming={setNaming}
                    onRename={() => ask(r.id, version, r.name)}
                    onConfirm={() => apply({ kind: "confirm", resource: r.id })}
                    saveName={saveName}
                    saveOff={saveOff}
                    saving={editing}
                    dragging={dragging}
                  />
                ))}
                {adding && (
                  <div className="flex items-center gap-2.5 border-b border-gray-100 py-2.5 pl-8 pr-4">
                    <FolderPlus size={14} className="shrink-0 text-gray-400" />
                    <NameField
                      label={t("gen.layout.newResource.name")}
                      naming={adding}
                      setNaming={setNaming}
                      save={saveName}
                      saveOff={saveOff}
                      saving={editing}
                    />
                  </div>
                )}
                {unassigned.length > 0 && (
                  <EndpointList
                    label={t("gen.layout.unassigned")}
                    hint={t("gen.layout.unassigned.hint", { version })}
                    endpoints={unassigned}
                    version={version}
                    canWrite={canWrite}
                    dragging={dragging}
                  />
                )}
              </div>
            )}
          </section>
        );
      })}

      {stored.no_version.length > 0 && (
        <section
          aria-label={t("gen.layout.noVersion")}
          className="mb-4 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm"
        >
          <EndpointList
            label={t("gen.layout.noVersion")}
            hint={t("gen.layout.noVersion.hint")}
            endpoints={stored.no_version}
            version={null}
            canWrite={canWrite}
            dragging={dragging}
          />
        </section>
      )}

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white px-3.5 py-3 text-xs text-gray-500">
        {t("gen.layout.footer")}
        <Link
          to={cardTo}
          state={fromList}
          className="ml-auto inline-flex items-center gap-1.5 rounded border border-pink-300 bg-pink-50 px-3 py-1.5 text-xs font-semibold text-brand transition hover:border-brand"
        >
          <Play size={12} /> {t("gen.layout.back")}
        </Link>
      </div>
    </div>
  );
}
