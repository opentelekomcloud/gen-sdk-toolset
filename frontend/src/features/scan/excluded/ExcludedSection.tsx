import { ODSButton } from "@telekom-ods/react-ui-kit/ODSButton";
import { useState } from "react";
import { ODSArrowUTurnBackwards, ODSCollapseDown, ODSNavigationRight, ODSStatusInactive } from "@telekom-ods/react-icons";
import { useExcluded } from "../api/queries";
import { useInclude } from "../api/mutations";
import type { ExcludedService } from "../../../shared/api/types";
import { useSession } from "../../../shared/auth/useSession";
import { useI18n } from "../../../shared/i18n";

function ExcludedRow({ item }: { item: ExcludedService }) {
  const include = useInclude(item.name);
  const [confirming, setConfirming] = useState(false);
  const { canWrite } = useSession();
  const { t } = useI18n();
  return (
    <div className="border-b border-neutral-100 last:border-0">
      <div className="flex items-center gap-4 px-4 py-2.5">
        <span className="w-44 truncate font-mono text-sm text-neutral-700" title={item.name}>
          {item.name}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs text-ink-recessive" title={item.reason}>
            {item.reason}
          </div>
          <div className="font-mono text-[10px] text-neutral-600">
            {t("excluded.by", { by: item.excluded_by, at: item.excluded_at })}
          </div>
        </div>
        {canWrite && (
          <ODSButton
            size="small"
            variant="outline"
            label={t("excluded.restore")}
            buttonIcon={<ODSArrowUTurnBackwards decorative />}
            leftIcon
            onClick={() => setConfirming(true)}
            disabled={include.isPending || confirming}
          />
        )}
      </div>
      {/* inline confirmation — same pattern as the snapshot selector, instead of window.confirm */}
      {confirming && canWrite && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-warning-line bg-warning-subtle px-4 py-2">
          <span className="whitespace-pre-line text-xs leading-relaxed text-warning">
            {t("excluded.restoreConfirm", { name: item.name })}
          </span>
          <span className="flex shrink-0 gap-2">
            <ODSButton size="small" variant="outline" label={t("exclude.cancel")} onClick={() => setConfirming(false)} />
            <ODSButton
              size="small"
              label={t("excluded.restore")}
              onClick={() => {
                setConfirming(false);
                include.mutate();
              }}
              disabled={include.isPending}
            />
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
      <button type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs font-medium text-neutral-600 transition hover:text-ink-recessive"
      >
        {open ? <ODSCollapseDown decorative size={13} /> : <ODSNavigationRight decorative size={13} />}
        <ODSStatusInactive decorative size={12} /> {t("excluded.title")} <span className="font-mono tabular-nums">{excluded.length}</span>
      </button>
      {open &&
        (excluded.length === 0 ? (
          <div className="mt-2 rounded-lg border border-dashed border-neutral-200 px-4 py-3 text-xs text-neutral-600">
            {t("excluded.empty")}
          </div>
        ) : (
          <div className="mt-2 overflow-hidden rounded-xl border border-neutral-200 bg-surface">
            {excluded.map((r) => (
              <ExcludedRow key={r.name} item={r} />
            ))}
          </div>
        ))}
    </div>
  );
}
