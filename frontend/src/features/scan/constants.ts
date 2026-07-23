import type { Section } from "./api/types.local";

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

export const SECTION_LABELS: Record<Section, string> = {
  path_params: "Path params",
  query_params: "Query params",
  headers: "Headers",
  body: "Body",
  response: "Response",
  example_request: "Example req",
  example_response: "Example resp",
};

/** Identity is self-reported, from environment config — never a literal in components. */
export const CONFIG = {
  identity: (import.meta.env.VITE_PANEL_IDENTITY as string | undefined) ?? "anonymous",
} as const;
