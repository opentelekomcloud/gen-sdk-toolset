import { AlertTriangle, ArrowLeft, Loader2, RefreshCw, type LucideIcon } from "lucide-react";
import { Link } from "react-router";
import type { ReactNode } from "react";
import { useRetry, type Retryable } from "../api/queries";
import { useI18n } from "../../../shared/i18n";

/**
 * "All services": from a service page back to the list of its panel, or - with
 * its own `label` - to the page above. `state` goes along, for what that page
 * keeps outside its address.
 */
export function ServiceBackLink({ to, state, label }: { to: string; state?: unknown; label?: string }) {
  const { t } = useI18n();
  return (
    <Link to={to} state={state} className="mb-3 flex items-center gap-1.5 text-sm text-gray-500 transition hover:text-gray-900">
      <ArrowLeft size={15} /> {label ?? t("service.back")}
    </Link>
  );
}

/**
 * A warning above a page's content: its `title`, what it says, and the one
 * thing to do about it. It comes up on its own - a refusal, a change someone
 * else made - so it is announced.
 */
export function NoticeBanner({
  title,
  children,
  action,
  onAction,
}: {
  title: string;
  children: ReactNode;
  action: string;
  onAction: () => void;
}) {
  return (
    <div
      role="status"
      className="mb-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800"
    >
      <AlertTriangle size={14} className="mt-px shrink-0 text-amber-500" />
      <div className="min-w-0">
        <span className="font-semibold">{title}</span>
        {" — "}
        {children}
      </div>
      <button type="button"
        onClick={onAction}
        className="ml-auto shrink-0 rounded border border-amber-300 px-2 py-1 font-medium text-amber-800 transition hover:border-amber-500 hover:bg-white"
      >
        {action}
      </button>
    </div>
  );
}

/**
 * A refused mutation changes nothing on screen, so say why it did not take:
 * `title` is the line for the case, `message` the refusal's own wording.
 */
export function RefusalBanner({ title, message, onDismiss }: { title: string; message: string; onDismiss: () => void }) {
  const { t } = useI18n();
  return (
    <NoticeBanner title={title} action={t("snap.dismiss")} onAction={onDismiss}>
      <span className="font-mono">{message}</span>
    </NoticeBanner>
  );
}

/** A block inside a page while its own data is on the way; the page around it stays. */
export function BlockLoading({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 py-3 text-xs text-gray-500">
      <Loader2 size={14} className="animate-spin text-gray-400" /> {label}
    </div>
  );
}

/**
 * A block inside a page whose own data did not load: what failed, and a retry.
 * An alert, so a screen reader announces it: the block replaces content that
 * would otherwise just be missing, and silence would read as "nothing here".
 */
export function BlockLoadFailed({ label, onRetry }: { label: string; onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="flex items-center justify-between rounded border border-red-200 bg-red-50 px-3 py-2">
      <span className="flex items-center gap-2 text-xs text-red-700">
        <AlertTriangle size={13} /> {label}
      </span>
      <button type="button"
        onClick={onRetry}
        className="flex items-center gap-1 rounded border border-red-300 px-2 py-1 text-xs font-medium text-red-700 transition hover:border-red-500"
      >
        <RefreshCw size={11} /> {t("service.retry")}
      </button>
    </div>
  );
}

/**
 * What a block shows in place of its data when it did not load, on the first
 * load or on a refresh (ADR-0081): the failure and a Retry. TanStack Query
 * keeps the last answer through a failed refresh; the block shows this instead,
 * so that answer is not read as current. While the Retry runs the block says
 * it is loading, so the click visibly did something and cannot be repeated.
 */
export function BlockFailed({
  query,
  label,
  loadingLabel,
}: {
  query: Retryable;
  label: string;
  loadingLabel: string;
}) {
  const { retrying, retry } = useRetry(query);
  return retrying ? <BlockLoading label={loadingLabel} /> : <BlockLoadFailed label={label} onRetry={retry} />;
}

/**
 * A collapsible list at the bottom of a page whose data did not load: its
 * title, without the count it no longer has, and the failure under it, folded
 * or not.
 */
export function SectionFailed({
  icon: Icon,
  title,
  className,
  ...failed
}: {
  icon: LucideIcon;
  title: string;
  className: string;
  query: Retryable;
  label: string;
  loadingLabel: string;
}) {
  return (
    <div className={className}>
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-gray-400">
        <Icon size={12} /> {title}
      </div>
      <BlockFailed {...failed} />
    </div>
  );
}

/** A service page while its data is on the way. */
export function ServiceLoading() {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center gap-2 py-24 text-sm text-gray-400">
      <Loader2 size={16} className="animate-spin" /> {t("service.loading")}
    </div>
  );
}

/** A service page with a card in place of its content: the way back, a line saying why, and what follows it. */
function ServiceStateCard({
  back,
  backState,
  label,
  children,
}: {
  back: string;
  backState?: unknown;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <ServiceBackLink to={back} state={backState} />
      <div className="rounded-xl border border-gray-200 bg-white p-10 text-center">
        <AlertTriangle size={22} className="mx-auto mb-2 text-gray-400" />
        <div className="mb-1 text-sm font-semibold text-gray-700">{label}</div>
        {children}
      </div>
    </div>
  );
}

/**
 * A service page that says `label` in place of its content, with a Retry: for a
 * load that failed, or an answer that leaves the page nothing to show.
 */
export function ServiceRetryCard({
  back,
  backState,
  label,
  onRetry,
}: {
  back: string;
  backState?: unknown;
  label: string;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  return (
    <ServiceStateCard back={back} backState={backState} label={label}>
      <button type="button"
        onClick={onRetry}
        className="mx-auto mt-2 flex items-center gap-1 rounded border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500"
      >
        <RefreshCw size={11} /> {t("service.retry")}
      </button>
    </ServiceStateCard>
  );
}

/**
 * A service page whose data did not load: the way back, with its `backState`,
 * and a retry. A service the server does not know - `notFound`, its name - gets
 * a hint instead, since retrying would not bring it back.
 */
export function ServiceLoadFailed({
  back,
  backState,
  onRetry,
  notFound,
}: {
  back: string;
  backState?: unknown;
  onRetry: () => void;
  notFound?: string;
}) {
  const { t } = useI18n();
  if (notFound == null) {
    return <ServiceRetryCard back={back} backState={backState} label={t("service.loadFailed")} onRetry={onRetry} />;
  }
  return (
    <ServiceStateCard back={back} backState={backState} label={t("service.notFound", { name: notFound })}>
      <div className="text-xs text-gray-500">{t("service.notFoundHint")}</div>
    </ServiceStateCard>
  );
}
