import type { ScanStatus } from "../../shared/api/types";
import type { DocStatus, SectionStatus } from "./types";
import type { Tone } from "./lib/sectionTone";
import type { MessageKey } from "../../shared/i18n";

/**
 * Typed class maps (PS9). Adding a union member breaks compilation
 * until the corresponding map is updated — that is the point.
 * Labels live in i18n dictionaries (status.* keys); only classes live here.
 */

export const SCAN_PILL_CLS: Record<ScanStatus, string> = {
  scanned: "bg-success-subtle text-success border-success-line",
  partial: "bg-warning-subtle text-warning border-warning-line",
  failed: "bg-danger-subtle text-danger border-danger-line",
  not_scanned: "bg-neutral-100 text-neutral-700 border-neutral-200",
  scanning: "bg-info-subtle text-info border-info-line",
};

export const scanPillKey = (s: ScanStatus): MessageKey => `status.${s}` as MessageKey;

export const DOC_STATUS_CLS: Record<DocStatus, string> = {
  ok: "text-success",
  partial: "text-warning",
  failed: "text-danger",
  unsupported: "text-neutral-700",
};

export const SECTION_STATUS_CLS: Record<SectionStatus, string> = {
  ok: "text-success",
  partial: "text-warning",
  failed: "text-danger",
  skipped: "text-neutral-700",
  missing: "text-neutral-600",
};

export const TONE_BG: Record<Tone, string> = {
  ok: "bg-success",
  warn: "bg-warning-fill",
  bad: "bg-danger",
  failed: "bg-danger",
  empty: "bg-neutral-200",
};

/** HTTP method is an open set — fallback covers exotic methods. */
const METHOD_CLS: Record<string, string> = {
  GET: "bg-info-subtle text-info",
  POST: "bg-success-subtle text-success",
  PUT: "bg-warning-subtle text-warning",
  PATCH: "bg-warning-subtle text-warning",
  DELETE: "bg-danger-subtle text-danger",
};
export const methodCls = (m: string): string => METHOD_CLS[m] ?? "bg-neutral-100 text-ink-recessive";

export const structOkCls = (v: number | null): string =>
  v == null ? "text-neutral-600" : v >= 90 ? "text-success" : v >= 60 ? "text-warning" : "text-danger";

/** A filter chip in the ODS chip shape. ODS's own chips are dropdown filters or
 *  dismissible tags, not the single-choice toggles with counts used here. */
export const chipCls = (active: boolean): string =>
  `inline-flex h-8 items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium transition ${
    active ? "border-brand bg-brand text-on-brand" : "border-neutral-400 bg-surface text-ink-recessive hover:border-ink hover:text-ink"
  }`;
