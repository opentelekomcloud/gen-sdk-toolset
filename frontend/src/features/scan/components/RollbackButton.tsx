import { Undo2 } from "lucide-react";
import type { ServiceDetail } from "../api/types.local";

interface Props {
  service: ServiceDetail;
  onRollback: () => void;
}

/**
 * Enabled only when has_previous and not scanning (PS11).
 * Confirmation is required — the current generation becomes inactive.
 */
export function RollbackButton({ service, onRollback }: Props) {
  const scanning = service.scan_status === "scanning";
  const disabled = scanning || !service.has_previous;
  const title = !service.has_previous
    ? "No previous scan"
    : scanning
      ? "Not available while a scan job is running"
      : "Swap to the previous scan generation";
  const handle = () => {
    if (disabled) return;
    if (
      window.confirm(
        `Rollback ${service.name} to the previous scan generation?\n\nThe current generation becomes inactive. The operation is reversible until the next scan.`,
      )
    ) {
      onRollback();
    }
  };
  return (
    <button
      onClick={handle}
      title={title}
      disabled={disabled}
      className={`flex items-center gap-1.5 rounded border px-3 py-2 text-sm font-medium transition ${
        disabled
          ? "cursor-not-allowed border-gray-200 text-gray-300"
          : "border-gray-300 text-gray-600 hover:border-gray-500 hover:text-gray-900"
      }`}
    >
      <Undo2 size={14} /> Rollback
    </button>
  );
}
