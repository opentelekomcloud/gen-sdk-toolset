import { RefreshCw, ArrowUpCircle, GitCommit, type LucideIcon } from "lucide-react";
import type { RescanReason } from "../../../shared/api/types";
import type { MessageKey } from "../../../shared/i18n";

/**
 * rescan_reason is computed SERVER-side (PS2, priority retry → version → drift).
 * The client only maps it to presentation; labels are i18n keys (rescan.* —
 * `rescan.version` interpolates {v}). Keyed by the generated union, so a reason
 * the backend adds or drops breaks this map rather than passing unnoticed.
 */
export const RESCAN_META: Record<RescanReason, { icon: LucideIcon; labelKey: MessageKey; destructiveTone: boolean }> = {
  retry: { icon: RefreshCw, labelKey: "rescan.retry", destructiveTone: true },
  version: { icon: ArrowUpCircle, labelKey: "rescan.version", destructiveTone: false },
  drift: { icon: GitCommit, labelKey: "rescan.drift", destructiveTone: false },
};
