/* eslint-disable react-refresh/only-export-components -- i18n module: the
   provider component, the useI18n hook, and LOCALE belong together; a full HMR
   reload on dictionary edits is acceptable. */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { en } from "./en";
import { de } from "./de";

export type Lang = "en" | "de";
export type MessageKey = keyof typeof en;

/** BCP-47 locale per UI language — date/number formatting (Intl) keys off this. */
export const LOCALE: Record<Lang, string> = { en: "en-GB", de: "de-DE" };

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

/**
 * t("key", {vars}) — missing de keys fall back to en; unknown {holes} stay literal.
 * Pluralization: a template may hold two forms split by "|" ("{n} doc|{n} docs");
 * the branch is picked via Intl.PluralRules over vars.n (en and de both have
 * simple one/other rules).
 */
export function useI18n() {
  const { lang, setLang } = useContext(LangContext);
  const t = (key: MessageKey, vars?: Record<string, string | number>): string => {
    let template: string = DICTS[lang][key] ?? en[key];
    if (template.includes("|") && typeof vars?.n === "number") {
      const [one, other] = template.split("|");
      template = new Intl.PluralRules(LOCALE[lang]).select(vars.n) === "one" ? one : other;
    }
    return format(template, vars);
  };
  return { t, lang, setLang, locale: LOCALE[lang] };
}
