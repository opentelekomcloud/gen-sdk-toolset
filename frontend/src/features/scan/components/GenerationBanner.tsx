import { History } from "lucide-react";
import type { ServiceDetail } from "../api/types.local";
import { fmtGenAt } from "../lib/generation";
import { useI18n } from "../../../shared/i18n";

interface Props {
  service: ServiceDetail;
  onActivateLatest: () => void;
}

/** G1: shown when active_generation_id deliberately lags latest_generation_id — one-click return to latest. */
export function GenerationBanner({ service, onActivateLatest }: Props) {
  const { t } = useI18n();
  const active = service.active_generation;
  const latest = service.latest_generation;
  if (!active || !latest || active.id === latest.id) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800">
      <span className="flex items-center gap-2">
        <History size={14} />
        {t("genBanner.text", {
          activeId: active.id,
          at: fmtGenAt(active.created_at),
          ver: active.scanner_version,
          latestId: latest.id,
          latestAt: fmtGenAt(latest.created_at),
        })}
      </span>
      <button
        type="button"
        onClick={onActivateLatest}
        className="rounded border border-amber-300 bg-white px-2.5 py-1 font-medium text-amber-800 transition hover:border-amber-500"
      >
        {t("genBanner.activateLatest")}
      </button>
    </div>
  );
}
