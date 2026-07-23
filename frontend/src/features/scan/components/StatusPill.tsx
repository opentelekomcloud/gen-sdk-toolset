import { Loader2 } from "lucide-react";
import type { ScanStatus } from "../api/types.local";
import { SCAN_PILL_CLS, scanPillKey } from "../styles";
import { useI18n } from "../../../shared/i18n";

export function StatusPill({ kind, by }: { kind: ScanStatus; by?: string }) {
  const { t } = useI18n();
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${SCAN_PILL_CLS[kind]}`}>
      {kind === "scanning" && <Loader2 size={11} className="animate-spin" />}
      {t(scanPillKey(kind))}
      {kind === "scanning" && by ? ` · ${by}` : ""}
    </span>
  );
}
