import { Loader2 } from "lucide-react";
import type { ScanStatus } from "../api/types.local";
import { SCAN_PILL } from "../styles";

export function StatusPill({ kind, by }: { kind: ScanStatus; by?: string }) {
  const { label, cls } = SCAN_PILL[kind];
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {kind === "scanning" && <Loader2 size={11} className="animate-spin" />}
      {label}
      {kind === "scanning" && by ? ` · ${by}` : ""}
    </span>
  );
}
