import type { GenState } from "./data/types";
import type { MessageKey } from "../../shared/i18n";

/** The state pill's classes per state - the prototype's `GEN_PILL`; labels are the `gen.state.*` keys. */
export const GEN_STATE_CLS: Record<GenState, string> = {
  not_generated: "bg-gray-100 text-gray-500 border-gray-200",
  in_progress: "bg-blue-50 text-blue-700 border-blue-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  review: "bg-violet-50 text-violet-700 border-violet-200",
  partial: "bg-amber-50 text-amber-700 border-amber-200",
  done: "bg-violet-50 text-violet-700 border-violet-200",
};

export const genStateKey = (s: GenState): MessageKey => `gen.state.${s}` as MessageKey;
