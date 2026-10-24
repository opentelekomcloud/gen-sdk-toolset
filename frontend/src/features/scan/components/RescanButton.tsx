import { ODSButton } from "@telekom-ods/react-ui-kit/ODSButton";
import { Spinner } from "../../../shared/ui/Spinner";
import type { RescanReason } from "../../../shared/api/types";
import { RESCAN_META } from "../lib/rescan";
import { useI18n } from "../../../shared/i18n";

interface Props {
  reason: RescanReason | null;
  scanning?: { jobId?: number; startedBy?: string };
  scannerVersion: string;
  onClick: () => void;
  size?: "sm" | "lg";
}

/**
 * Three modes (PS10): scanning → job indicator; reason → button with icon by
 * kind; no reason → renders nothing. Parent stops row-click propagation.
 *
 * ODS has no red button, so a retry after a failure (`destructiveTone`) takes
 * the filled secondary variant: it still stands out from the outlined rescans
 * in the same column, by weight rather than by colour.
 */
export function RescanButton({ reason, scanning, scannerVersion, onClick, size = "sm" }: Props) {
  const { t } = useI18n();
  if (scanning) {
    return (
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-info">
        <Spinner />{" "}
        {scanning.jobId ? t("rescan.job", { id: scanning.jobId }) : t("rescan.queueing")}
        {scanning.startedBy ? ` · ${scanning.startedBy}` : ""}
      </span>
    );
  }
  if (!reason) return null;
  const meta = RESCAN_META[reason];
  const Icon = meta.icon;
  return (
    <ODSButton
      size="small"
      variant={size === "lg" ? "primary" : meta.destructiveTone ? "secondary" : "outline"}
      label={t(meta.labelKey, { v: scannerVersion })}
      buttonIcon={<Icon decorative />}
      leftIcon
      onClick={onClick}
    />
  );
}
