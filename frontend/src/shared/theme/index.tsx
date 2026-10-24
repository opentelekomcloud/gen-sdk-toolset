/* eslint-disable react-refresh/only-export-components -- theme module: the
   provider and the useTheme hook belong together, as in shared/i18n. */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

/** ODS `data-mode`: the whole app switches by this one attribute on <body>. */
export type Mode = "light" | "dark";

const STORAGE_KEY = "panel.mode";

const storedMode = (): Mode | null => {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : null;
};

const osMode = (): Mode => (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");

const ThemeContext = createContext<{ mode: Mode; setMode: (m: Mode) => void }>({ mode: "light", setMode: () => {} });

/**
 * A mode the user picked wins and is remembered; until then the panel follows
 * the operating system. Only a pick is stored - storing the OS value on the
 * first visit would freeze it, and a later OS switch would no longer show.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [chosen, setChosen] = useState<Mode | null>(storedMode);
  const mode = chosen ?? osMode();
  useEffect(() => {
    document.body.dataset.mode = mode;
    /* the root too: ODS gives :root `color-scheme: light dark`, which would
       keep scrollbars and overscroll in the OS mode, not the chosen one */
    document.documentElement.dataset.mode = mode;
  }, [mode]);
  const setMode = (m: Mode) => {
    localStorage.setItem(STORAGE_KEY, m);
    setChosen(m);
  };
  return <ThemeContext.Provider value={{ mode, setMode }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
