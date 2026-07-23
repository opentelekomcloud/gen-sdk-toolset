import { NavLink } from "react-router";

/** Shell-level nav. Add entries here as the Generation / Maintenance panels land. */
const NAV = [
  { label: "Scan", path: "/scan", enabled: true },
  { label: "Generation", path: "/generation", enabled: false },
  { label: "Maintenance", path: "/maintenance", enabled: false },
] as const;

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
  return (
    <nav className="flex items-end border-b border-gray-200 bg-white px-6">
      {NAV.map((item) =>
        item.enabled ? (
          /* NavLink sets aria-current="page" itself when active */
          <NavLink key={item.label} to={item.path} className={({ isActive }) => (isActive ? tabCls.active : tabCls.inactive)}>
            {item.label}
          </NavLink>
        ) : (
          <button key={item.label} disabled title="Coming soon" className={tabCls.disabled}>
            {item.label}
            <span className={badgeSoonCls}>soon</span>
          </button>
        ),
      )}
    </nav>
  );
}
