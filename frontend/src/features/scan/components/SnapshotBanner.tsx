import { ODSHistory } from "@telekom-ods/react-icons";
import { ODSInlineNotification } from "@telekom-ods/react-ui-kit/ODSInlineNotification";
import type { ServiceDetail } from "../../../shared/api/types";
import { fmtSnapshotAt } from "../lib/snapshot";
import { useI18n } from "../../../shared/i18n";

interface Props {
  service: ServiceDetail;
  onActivateLatest: () => void;
  /** A viewer is told which snapshot is being served, but cannot change it. */
  canActivate: boolean;
}

/** G1: shown when active_snapshot_id deliberately lags latest_snapshot_id — one-click return to latest. */
export function SnapshotBanner({ service, onActivateLatest, canActivate }: Props) {
  const { t, locale } = useI18n();
  const active = service.active_snapshot;
  const latest = service.latest_snapshot;
  if (!active || !latest || active.id === latest.id) return null;
  return (
    <ODSInlineNotification
      className="mb-4"
      mode="warning"
      warningIcon={<ODSHistory decorative />}
      showCloseButton={false}
      text={t("snapBanner.text", {
        activeId: active.id,
        at: fmtSnapshotAt(active.created_at, locale),
        ver: active.scanner_version,
        latestId: latest.id,
        latestAt: fmtSnapshotAt(latest.last_scanned_at, locale),
      })}
      link1Props={
        canActivate ? { label: t("snapBanner.activateLatest"), linkType: "button", onClick: onActivateLatest } : undefined
      }
    />
  );
}
