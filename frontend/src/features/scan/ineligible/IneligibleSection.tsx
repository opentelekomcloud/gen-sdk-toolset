import { useState } from "react";
import { ODSCollapseDown, ODSNavigationRight, ODSUnknown } from "@telekom-ods/react-icons";
import { useIneligible } from "../api/queries";
import type { Ineligible } from "../../../shared/api/types";
import { fmtSnapshotAt } from "../lib/snapshot";
import { useI18n } from "../../../shared/i18n";

function IneligibleRow({ item }: { item: Ineligible }) {
  const { t, locale } = useI18n();
  return (
    <div className="flex items-center gap-4 border-b border-neutral-100 px-4 py-2.5 last:border-0">
      <span className="w-44 truncate font-mono text-sm text-neutral-700" title={item.repo}>
        {item.repo}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs text-ink-recessive">{item.name}</div>
        <div className="font-mono text-[10px] text-neutral-600">
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
        className="flex items-center gap-1.5 text-xs font-medium text-neutral-600 transition hover:text-ink-recessive"
      >
        {open ? <ODSCollapseDown decorative size={13} /> : <ODSNavigationRight decorative size={13} />}
        <ODSUnknown decorative size={12} /> {t("ineligible.title")}{" "}
        <span className="font-mono tabular-nums">{ineligible.length}</span>
      </button>
      {open &&
        (ineligible.length === 0 ? (
          <div className="mt-2 rounded-lg border border-dashed border-neutral-200 px-4 py-3 text-xs text-neutral-600">
            {t("ineligible.empty")}
          </div>
        ) : (
          <div className="mt-2 overflow-hidden rounded-xl border border-neutral-200 bg-surface">
            {ineligible.map((r) => (
              <IneligibleRow key={r.repo} item={r} />
            ))}
          </div>
        ))}
    </div>
  );
}
