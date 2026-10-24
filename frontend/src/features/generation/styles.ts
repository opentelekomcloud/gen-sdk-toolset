import type { GenState } from "./data/types";
import type { MessageKey } from "../../shared/i18n";

/** The state pill's classes per state - the prototype's `GEN_PILL`; labels are the `gen.state.*` keys. */
export const GEN_STATE_CLS: Record<GenState, string> = {
  not_generated: "bg-neutral-100 text-neutral-700 border-neutral-200",
  in_progress: "bg-info-subtle text-info border-info-line",
  failed: "bg-danger-subtle text-danger border-danger-line",
  review: "bg-brand-subtle text-on-brand-subtle border-brand-line",
  partial: "bg-warning-subtle text-warning border-warning-line",
  done: "bg-brand-subtle text-on-brand-subtle border-brand-line",
};

export const genStateKey = (s: GenState): MessageKey => `gen.state.${s}` as MessageKey;
