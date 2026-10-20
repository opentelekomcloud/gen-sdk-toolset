import { ODSArrowLeft, ODSRefresh, ODSWarning } from "@telekom-ods/react-icons";
import { ODSButton } from "@telekom-ods/react-ui-kit/ODSButton";
import { ODSInlineNotification } from "@telekom-ods/react-ui-kit/ODSInlineNotification";
import { ODSLink } from "@telekom-ods/react-ui-kit/ODSLink";
import { RouterAnchor } from "../../../shared/ui/RouterAnchor";
import { Spinner } from "../../../shared/ui/Spinner";
import { useI18n } from "../../../shared/i18n";

/**
 * "All services": from a service page back to the list of its panel, or - with
 * its own `label` - to the page above. `state` goes along, for what that page
 * keeps outside its address.
 */
export function ServiceBackLink({ to, state, label }: { to: string; state?: unknown; label?: string }) {
  const { t } = useI18n();
  return (
    <div className="mb-3">
      <ODSLink
        Component={RouterAnchor}
        href={to}
        data-state={state}
        label={label ?? t("service.back")}
        leftIcon={<ODSArrowLeft decorative small />}
      />
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
    <ODSInlineNotification
      className="mb-4"
      mode="warning"
      title={title}
      text={message}
      onClose={onDismiss}
      buttonProps={{ "aria-label": t("snap.dismiss") }}
    />
  );
}

/** A block inside a page while its own data is on the way; the page around it stays. */
export function BlockLoading({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 py-3 text-xs text-neutral-700">
      <Spinner /> {label}
    </div>
  );
}

/** A block inside a page whose own data did not load: what failed, and a retry. */
export function BlockLoadFailed({ label, onRetry }: { label: string; onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-danger-line bg-danger-subtle px-3 py-2">
      <span className="flex items-center gap-2 text-xs text-danger">
        <ODSWarning decorative size={14} /> {label}
      </span>
      <ODSButton
        size="small"
        variant="outline"
        label={t("service.retry")}
        buttonIcon={<ODSRefresh decorative />}
        leftIcon
        onClick={onRetry}
      />
    </div>
  );
}

/** A service page while its data is on the way. */
export function ServiceLoading() {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center gap-2 py-24 text-sm text-neutral-600">
      <Spinner /> {t("service.loading")}
    </div>
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
  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <ServiceBackLink to={back} state={backState} />
      <div className="flex flex-col items-center rounded-xl border border-neutral-200 bg-surface p-10 text-center">
        <ODSWarning decorative size={24} className="mb-2 text-neutral-600" />
        <div className="mb-1 text-sm font-semibold text-ink-recessive">
          {notFound != null ? t("service.notFound", { name: notFound }) : t("service.loadFailed")}
        </div>
        {notFound != null ? (
          <div className="text-xs text-neutral-700">{t("service.notFoundHint")}</div>
        ) : (
          <ODSButton
            className="mt-2"
            size="small"
            variant="outline"
            label={t("service.retry")}
            buttonIcon={<ODSRefresh decorative />}
            leftIcon
            onClick={onRetry}
          />
        )}
      </div>
    </div>
  );
}
