import { RefreshCw, ArrowUpCircle, GitCommit, type LucideIcon } from "lucide-react";
import type { RescanReason } from "../api/types.local";
import type { MessageKey } from "../../../shared/i18n";

/**
 * rescan_reason is computed SERVER-side (PS2, priority retry → partial →
 * version → drift). The client only maps it to presentation; labels are
 * i18n keys (rescan.* — `rescan.version` interpolates {v}).
 */
export const RESCAN_META: Record<RescanReason, { icon: LucideIcon; labelKey: MessageKey; destructiveTone: boolean }> = {
  retry: { icon: RefreshCw, labelKey: "rescan.retry", destructiveTone: true },
  partial: { icon: RefreshCw, labelKey: "rescan.partial", destructiveTone: false },
  version: { icon: ArrowUpCircle, labelKey: "rescan.version", destructiveTone: false },
  drift: { icon: GitCommit, labelKey: "rescan.drift", destructiveTone: false },
};
