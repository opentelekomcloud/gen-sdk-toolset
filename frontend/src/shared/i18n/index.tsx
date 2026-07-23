import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { en } from "./en";
import { de } from "./de";

export type Lang = "en" | "de";
export type MessageKey = keyof typeof en;

const DICTS: Record<Lang, Record<MessageKey, string>> = { en, de };
const STORAGE_KEY = "panel.lang";

const format = (template: string, vars?: Record<string, string | number>): string =>
  vars ? template.replace(/\{(\w+)\}/g, (m, k: string) => (vars[k] != null ? String(vars[k]) : m)) : template;

const initialLang = (): Lang => {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "de") return stored;
  return navigator.language.toLowerCase().startsWith("de") ? "de" : "en";
};

const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "en", setLang: () => {} });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(initialLang);
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, lang);
    document.documentElement.lang = lang;
  }, [lang]);
  return <LangContext.Provider value={{ lang, setLang }}>{children}</LangContext.Provider>;
}

/** t("key", {vars}) — missing ru keys fall back to en; unknown {holes} stay literal. */
export function useI18n() {
  const { lang, setLang } = useContext(LangContext);
  const t = (key: MessageKey, vars?: Record<string, string | number>): string =>
    format(DICTS[lang][key] ?? en[key], vars);
  return { t, lang, setLang };
}
