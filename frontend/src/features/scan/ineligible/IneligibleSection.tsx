import { useState } from "react";
import { ChevronDown, ChevronRight, FileQuestion } from "lucide-react";
import { useIneligible } from "../api/queries";
import type { Ineligible } from "../../../shared/api/types";
import { fmtSnapshotAt } from "../lib/snapshot";
import { useI18n } from "../../../shared/i18n";

function IneligibleRow({ item }: { item: Ineligible }) {
  const { t, locale } = useI18n();
  return (
    <div className="flex items-center gap-4 border-b border-gray-100 px-4 py-2.5 last:border-0">
      <span className="w-44 truncate font-mono text-sm text-gray-500" title={item.repo}>
        {item.repo}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs text-gray-600">{item.name}</div>
        <div className="font-mono text-[10px] text-gray-400">
          {/* A missing timestamp says so in words: fmtSnapshotAt would render it
              as "—", which beside "checked" reads as a date we failed to load. */}
          {item.checked_at
            ? t("ineligible.checked", {
                branch: item.branch,
                at: fmtSnapshotAt(item.checked_at, locale),
              })
            : t("ineligible.neverChecked", { branch: item.branch })}
        </div>
      </div>
    </div>
  );
}

/** Collapsed managed list at the bottom of the registry, beside the excluded
 *  one. Read-only on purpose: nobody decided this, a lookup did, and it
 *  reverses itself the next time discovery finds the API-reference path. */
export function IneligibleSection() {
  const [open, setOpen] = useState(false);
  const { data: ineligible } = useIneligible();
  const { t } = useI18n();
  if (!ineligible) return null;

  return (
    <div className="mt-3">
      <button type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs font-medium text-gray-400 transition hover:text-gray-600"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <FileQuestion size={12} /> {t("ineligible.title")}{" "}
        <span className="font-mono tabular-nums">{ineligible.length}</span>
      </button>
      {open &&
        (ineligible.length === 0 ? (
          <div className="mt-2 rounded-lg border border-dashed border-gray-200 px-4 py-3 text-xs text-gray-400">
            {t("ineligible.empty")}
          </div>
        ) : (
          <div className="mt-2 overflow-hidden rounded-xl border border-gray-200 bg-white">
            {ineligible.map((r) => (
              <IneligibleRow key={r.repo} item={r} />
            ))}
          </div>
        ))}
    </div>
  );
}
