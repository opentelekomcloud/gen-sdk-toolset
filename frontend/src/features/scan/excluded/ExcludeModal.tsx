import { useEffect, useState } from "react";
import { Ban } from "lucide-react";
import type { RescanReason, ServiceDetail } from "../api/types.local";
import { CONFIG } from "../constants";
import { RESCAN_META } from "../lib/rescan";

interface Props {
  service: ServiceDetail;
  onConfirm: (reason: string) => void;
  onClose: () => void;
}

/** Confirmation with a mandatory reason (PS19). Identity is self-reported config. */
export function ExcludeModal({ service, onConfirm, onClose }: Props) {
  const [reason, setReason] = useState("");
  const attention: RescanReason | null = service.rescan_reason;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-gray-900">
          <Ban size={15} className="text-gray-400" /> Exclude {service.name} from the registry
        </div>
        <p className="mb-3 text-xs leading-relaxed text-gray-500">
          The service disappears from the table, chips, and header stats; nightly discovery will skip it. Scan history
          is kept — restoring brings everything back.
          {attention && (
            <span className="text-amber-700">
              {" "}
              This service currently requires attention ({RESCAN_META[attention].label("current").toLowerCase()}) —
              excluding removes it from those counts too.
            </span>
          )}
        </p>
        <label className="mb-1 block text-xs font-medium text-gray-600">
          Reason <span className="text-red-500">*</span>
        </label>
        <textarea
          autoFocus
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="Why is this repo out of scope?"
          className="w-full rounded-md border border-gray-300 p-2 text-sm outline-none transition focus:border-gray-500"
        />
        <div className="mt-3 flex items-center justify-between">
          <span className="font-mono text-[10px] text-gray-400">
            recorded as {CONFIG.identity} · {today}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:border-gray-500"
            >
              Cancel
            </button>
            <button
              disabled={!reason.trim()}
              onClick={() => onConfirm(reason.trim())}
              className={`rounded px-3 py-1.5 text-xs font-semibold text-white transition ${
                reason.trim() ? "bg-gray-900 hover:bg-gray-700" : "cursor-not-allowed bg-gray-300"
              }`}
            >
              Exclude service
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
