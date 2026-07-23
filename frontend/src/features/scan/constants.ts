import type { Section } from "./api/types.local";
import type { MessageKey } from "../../shared/i18n";

/** The 7 sections in fixed order (PS1). */
export const SECTIONS: readonly Section[] = [
  "path_params",
  "query_params",
  "headers",
  "body",
  "response",
  "example_request",
  "example_response",
] as const;

/** i18n key for a section label (dictionaries hold section.* entries). */
export const sectionLabelKey = (s: Section): MessageKey => `section.${s}` as MessageKey;

/** Identity is self-reported, from environment config — never a literal in components. */
export const CONFIG = {
  identity: (import.meta.env.VITE_PANEL_IDENTITY as string | undefined) ?? "anonymous",
} as const;
