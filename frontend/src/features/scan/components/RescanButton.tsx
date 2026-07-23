import { Loader2 } from "lucide-react";
import type { RescanReason } from "../api/types.local";
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
 */
export function RescanButton({ reason, scanning, scannerVersion, onClick, size = "sm" }: Props) {
  const { t } = useI18n();
  if (scanning) {
    return (
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-blue-600">
        <Loader2 size={12} className="animate-spin" />{" "}
        {scanning.jobId ? t("rescan.job", { id: scanning.jobId }) : t("rescan.queueing")}
        {scanning.startedBy ? ` · ${scanning.startedBy}` : ""}
      </span>
    );
  }
  if (!reason) return null;
  const meta = RESCAN_META[reason];
  const Icon = meta.icon;
  const label = t(meta.labelKey, { v: scannerVersion });
  if (size === "lg") {
    return (
      <button
        onClick={onClick}
        className="flex items-center gap-1.5 rounded bg-brand px-3.5 py-2 text-sm font-semibold text-white transition hover:opacity-90"
      >
        <Icon size={14} /> {label}
      </button>
    );
  }
  const tone = meta.destructiveTone
    ? "border-red-300 text-red-700 hover:border-red-500"
    : "border-gray-300 text-gray-600 hover:border-gray-500 hover:text-gray-900";
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-2.5 py-1 text-xs font-medium transition ${tone}`}
    >
      <Icon size={12} /> {label}
    </button>
  );
}
