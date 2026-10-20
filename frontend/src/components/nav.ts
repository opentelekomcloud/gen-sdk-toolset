import type { MessageKey } from "../shared/i18n";

/** Shell-level nav, shared by the header menu and the narrow-screen tab row. Add entries here as panels land. */
export const NAV: { key: MessageKey; path: string; enabled: boolean }[] = [
  { key: "tab.scan", path: "/scan", enabled: true },
  { key: "tab.generation", path: "/generation", enabled: true },
  { key: "tab.maintenance", path: "/maintenance", enabled: false },
];

/** Whether `pathname` is the panel at `path` or a page inside it. */
export const inPanel = (pathname: string, path: string): boolean =>
  pathname === path || pathname.startsWith(`${path}/`);
