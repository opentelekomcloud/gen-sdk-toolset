import { Loader2 } from "lucide-react";
import type { ScanStatus } from "../../../shared/api/types";
import { SCAN_PILL_CLS, scanPillKey } from "../styles";
import { useI18n } from "../../../shared/i18n";

/** A scan state by name, or another panel's state with its own classes and label. */
type StatusPillProps = { kind: ScanStatus } | { cls: string; label: string; running: boolean };

/**
 * The state pill shared by the panels. For a scan it shows the state and nothing else:
 * who started a running scan is shown where the job number is - putting it here too
 * stretched the pill past its column.
 */
export function StatusPill(props: StatusPillProps) {
  const { t } = useI18n();
  const { cls, label, running } =
    "kind" in props
      ? { cls: SCAN_PILL_CLS[props.kind], label: t(scanPillKey(props.kind)), running: props.kind === "scanning" }
      : props;
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {running && <Loader2 size={11} className="animate-spin" />}
      {label}
    </span>
  );
}
