import { AlertTriangle, ArrowLeft, Loader2, RefreshCw } from "lucide-react";
import { Link } from "react-router";
import { useI18n } from "../../../shared/i18n";

/** "All services": from a service page back to the list of its panel. */
export function ServiceBackLink({ to }: { to: string }) {
  const { t } = useI18n();
  return (
    <Link to={to} className="mb-3 flex items-center gap-1.5 text-sm text-gray-500 transition hover:text-gray-900">
      <ArrowLeft size={15} /> {t("service.back")}
    </Link>
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

/**
 * A service page whose data did not load: the way back and a retry. A service
 * the server does not know - `notFound`, its name - gets a hint instead, since
 * retrying would not bring it back.
 */
export function ServiceLoadFailed({
  back,
  onRetry,
  notFound,
}: {
  back: string;
  onRetry: () => void;
  notFound?: string;
}) {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      <ServiceBackLink to={back} />
      <div className="rounded-xl border border-gray-200 bg-white p-10 text-center">
        <AlertTriangle size={22} className="mx-auto mb-2 text-gray-400" />
        <div className="mb-1 text-sm font-semibold text-gray-700">
          {notFound != null ? t("service.notFound", { name: notFound }) : t("service.loadFailed")}
        </div>
        {notFound != null ? (
          <div className="text-xs text-gray-500">{t("service.notFoundHint")}</div>
        ) : (
          <button type="button"
            onClick={onRetry}
            className="mx-auto mt-2 flex items-center gap-1 rounded border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500"
          >
            <RefreshCw size={11} /> {t("service.retry")}
          </button>
        )}
      </div>
    </div>
  );
}
