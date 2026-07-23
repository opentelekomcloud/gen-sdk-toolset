import type { DocStatus, ScanStatus, SectionStatus } from "./api/types.local";
import type { Tone } from "./lib/sectionTone";
import type { MessageKey } from "../../shared/i18n";

/**
 * Typed class maps (PS9). Adding a union member breaks compilation
 * until the corresponding map is updated — that is the point.
 * Labels live in i18n dictionaries (status.* keys); only classes live here.
 */

export const SCAN_PILL_CLS: Record<ScanStatus, string> = {
  scanned: "bg-emerald-50 text-emerald-700 border-emerald-200",
  partial: "bg-amber-50 text-amber-700 border-amber-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  not_scanned: "bg-gray-100 text-gray-500 border-gray-200",
  scanning: "bg-blue-50 text-blue-700 border-blue-200",
};

export const scanPillKey = (s: ScanStatus): MessageKey => `status.${s}` as MessageKey;

export const DOC_STATUS_CLS: Record<DocStatus, string> = {
  ok: "text-emerald-700",
  partial: "text-amber-700",
  failed: "text-red-700",
  unsupported: "text-gray-500",
};

export const SECTION_STATUS_CLS: Record<SectionStatus, string> = {
  ok: "text-emerald-700",
  partial: "text-amber-700",
  failed: "text-red-700",
  skipped: "text-gray-500",
  missing: "text-gray-400",
};

export const TONE_BG: Record<Tone, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-400",
  bad: "bg-red-500",
  failed: "bg-red-600",
  empty: "bg-gray-200",
};

/** HTTP method is an open set — fallback covers exotic methods. */
const METHOD_CLS: Record<string, string> = {
  GET: "bg-blue-50 text-blue-700",
  POST: "bg-emerald-50 text-emerald-700",
  PUT: "bg-amber-50 text-amber-700",
  PATCH: "bg-amber-50 text-amber-700",
  DELETE: "bg-red-50 text-red-700",
};
export const methodCls = (m: string): string => METHOD_CLS[m] ?? "bg-gray-100 text-gray-600";

export const structOkCls = (v: number | null): string =>
  v == null ? "text-gray-400" : v >= 90 ? "text-emerald-700" : v >= 60 ? "text-amber-700" : "text-red-700";

export const chipCls = (active: boolean): string =>
  `rounded-full border px-3 py-1 text-xs font-medium transition ${
    active ? "border-transparent bg-brand text-white" : "border-gray-300 bg-white text-gray-600 hover:border-gray-400"
  }`;
