import { useState } from "react";
import { Ban, ChevronDown, ChevronRight, Undo2 } from "lucide-react";
import { useExcluded } from "../api/queries";
import { useInclude } from "../api/mutations";
import type { ExcludedService } from "../api/types.local";
import { useI18n } from "../../../shared/i18n";

function ExcludedRow({ item }: { item: ExcludedService }) {
  const include = useInclude(item.name);
  const [confirming, setConfirming] = useState(false);
  const { t } = useI18n();
  return (
    <div className="border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-4 px-4 py-2.5">
        <span className="w-44 truncate font-mono text-sm text-gray-500" title={item.name}>
          {item.name}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs text-gray-600" title={item.reason}>
            {item.reason}
          </div>
          <div className="font-mono text-[10px] text-gray-400">
            {t("excluded.by", { by: item.excluded_by, at: item.excluded_at })}
          </div>
        </div>
        <button
          onClick={() => setConfirming(true)}
          disabled={include.isPending || confirming}
          className="flex items-center gap-1.5 whitespace-nowrap rounded border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-gray-500 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Undo2 size={12} /> {t("excluded.restore")}
        </button>
      </div>
      {/* inline confirmation — same pattern as the generation selector, instead of window.confirm */}
      {confirming && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-amber-100 bg-amber-50 px-4 py-2">
          <span className="whitespace-pre-line text-xs leading-relaxed text-amber-800">
            {t("excluded.restoreConfirm", { name: item.name })}
          </span>
          <span className="flex shrink-0 gap-2">
            <button
              onClick={() => setConfirming(false)}
              className="rounded border border-amber-300 px-2.5 py-1 text-xs font-medium text-amber-800 transition hover:border-amber-500"
            >
              {t("exclude.cancel")}
            </button>
            <button
              onClick={() => {
                setConfirming(false);
                include.mutate();
              }}
              disabled={include.isPending}
              className="rounded bg-brand px-2.5 py-1 text-xs font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("excluded.restore")}
            </button>
          </span>
        </div>
      )}
    </div>
  );
}

/** Collapsed managed list at the bottom of the registry (PS19). */
export function ExcludedSection() {
  const [open, setOpen] = useState(false);
  const { data: excluded } = useExcluded();
  const { t } = useI18n();
  if (!excluded) return null;

  return (
    <div className="mt-6">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs font-medium text-gray-400 transition hover:text-gray-600"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Ban size={12} /> {t("excluded.title")} <span className="font-mono tabular-nums">{excluded.length}</span>
      </button>
      {open &&
        (excluded.length === 0 ? (
          <div className="mt-2 rounded-lg border border-dashed border-gray-200 px-4 py-3 text-xs text-gray-400">
            {t("excluded.empty")}
          </div>
        ) : (
          <div className="mt-2 overflow-hidden rounded-xl border border-gray-200 bg-white">
            {excluded.map((r) => (
              <ExcludedRow key={r.name} item={r} />
            ))}
          </div>
        ))}
    </div>
  );
}
