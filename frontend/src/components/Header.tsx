import { Activity } from "lucide-react";
import { useSummary } from "../features/scan/api/queries";

/** Logo + pills from summary; no bulk actions here by design (PS9). */
export function Header() {
  const { data: summary } = useSummary();
  return (
    <header className="flex items-center justify-between bg-brand px-6 py-3">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-sm bg-white text-xl font-black text-brand">T</div>
        <div className="text-white">
          <div className="text-sm font-semibold leading-tight">gen-sdk-tooling</div>
          <div className="text-xs leading-tight opacity-80">Service scan registry · T Cloud Public</div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        {summary && summary.scans_running > 0 && (
          <span className="flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-xs text-white">
            <Activity size={12} className="animate-pulse" /> {summary.scans_running} scan
            {summary.scans_running > 1 ? "s" : ""} running
          </span>
        )}
        {summary && (
          <span className="rounded-full bg-white/15 px-2.5 py-1 font-mono text-xs text-white">
            scanner v{summary.scanner_version}
          </span>
        )}
      </div>
    </header>
  );
}
