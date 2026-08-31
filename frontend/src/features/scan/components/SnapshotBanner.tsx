import { History } from "lucide-react";
import type { ServiceDetail } from "../../../shared/api/types";
import { fmtSnapshotAt } from "../lib/snapshot";
import { useI18n } from "../../../shared/i18n";

interface Props {
  service: ServiceDetail;
  onActivateLatest: () => void;
}

/** G1: shown when active_snapshot_id deliberately lags latest_snapshot_id — one-click return to latest. */
export function SnapshotBanner({ service, onActivateLatest }: Props) {
  const { t, locale } = useI18n();
  const active = service.active_snapshot;
  const latest = service.latest_snapshot;
  if (!active || !latest || active.id === latest.id) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800">
      <span className="flex items-center gap-2">
        <History size={14} />
        {t("snapBanner.text", {
          activeId: active.id,
          at: fmtSnapshotAt(active.created_at, locale),
          ver: active.scanner_version,
          latestId: latest.id,
          latestAt: fmtSnapshotAt(latest.last_scanned_at, locale),
        })}
      </span>
      <button
        type="button"
        onClick={onActivateLatest}
        className="rounded border border-amber-300 bg-white px-2.5 py-1 font-medium text-amber-800 transition hover:border-amber-500"
      >
        {t("snapBanner.activateLatest")}
      </button>
    </div>
  );
}
