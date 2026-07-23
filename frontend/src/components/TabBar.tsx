import { NavLink } from "react-router";
import { useI18n, type MessageKey } from "../shared/i18n";

/** Shell-level nav. Add entries here as the Generation / Maintenance panels land. */
const NAV: { key: MessageKey; path: string; enabled: boolean }[] = [
  { key: "tab.scan", path: "/scan", enabled: true },
  { key: "tab.generation", path: "/generation", enabled: false },
  { key: "tab.maintenance", path: "/maintenance", enabled: false },
];

const tabCls = {
  active: "-mb-px border-b-2 border-brand px-4 py-2.5 text-sm font-semibold text-brand",
  inactive:
    "-mb-px border-b-2 border-transparent px-4 py-2.5 text-sm font-medium text-gray-500 transition hover:text-gray-800",
  disabled:
    "-mb-px flex cursor-not-allowed items-center gap-1.5 border-b-2 border-transparent px-4 py-2.5 text-sm font-medium text-gray-300",
} as const;

const badgeSoonCls =
  "rounded-full bg-gray-100 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-gray-400";

export function TabBar() {
  const { t } = useI18n();
  return (
    <nav className="flex items-end border-b border-gray-200 bg-white px-6">
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
