import { NavLink } from "react-router";
import { useI18n } from "../shared/i18n";
import { NAV } from "./nav";

const tabCls = {
  active: "-mb-px border-b-[3px] border-brand px-4 py-2.5 text-sm font-bold text-ink",
  inactive:
    "-mb-px border-b-[3px] border-transparent px-4 py-2.5 text-sm font-medium text-ink-recessive transition hover:text-ink",
  disabled:
    "-mb-px flex cursor-not-allowed items-center gap-1.5 border-b-[3px] border-transparent px-4 py-2.5 text-sm font-medium text-neutral-400",
} as const;

const badgeSoonCls =
  "rounded-full bg-neutral-100 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-neutral-600";

/**
 * The panels as tabs, for narrow screens only: the ODS header shows its own
 * menu from the ODS laptop width up (`--viewport-laptop`, 65rem) and hides it
 * below, so this row takes over there and never doubles it.
 */
export function TabBar() {
  const { t } = useI18n();
  return (
    <nav aria-label={t("header.mainMenu")} className="flex items-end border-b border-neutral-200 bg-surface px-6 min-[65rem]:hidden">
      {NAV.map((item) =>
        item.enabled ? (
          /* NavLink sets aria-current="page" itself when active */
          <NavLink key={item.key} to={item.path} className={({ isActive }) => (isActive ? tabCls.active : tabCls.inactive)}>
            {t(item.key)}
          </NavLink>
        ) : (
          <button key={item.key} disabled title={t("tab.comingSoon")} className={tabCls.disabled}>
            {t(item.key)}
            <span className={badgeSoonCls}>{t("tab.soon")}</span>
          </button>
        ),
      )}
    </nav>
  );
}
