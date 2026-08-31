import { Loader2 } from "lucide-react";
import type { ScanStatus } from "../../../shared/api/types";
import { SCAN_PILL_CLS, scanPillKey } from "../styles";
import { useI18n } from "../../../shared/i18n";

/**
 * The scan state, and nothing else. Who started a running scan is shown where
 * the job number is - putting it here too stretched the pill past its column.
 */
export function StatusPill({ kind }: { kind: ScanStatus }) {
  const { t } = useI18n();
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${SCAN_PILL_CLS[kind]}`}
    >
      {kind === "scanning" && <Loader2 size={11} className="animate-spin" />}
      {t(scanPillKey(kind))}
    </span>
  );
}
