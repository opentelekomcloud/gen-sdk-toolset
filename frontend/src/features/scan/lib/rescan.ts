import { RefreshCw, ArrowUpCircle, GitCommit, type LucideIcon } from "lucide-react";
import type { RescanReason } from "../api/types.local";

/**
 * rescan_reason is computed SERVER-side (PS2, priority retry → partial →
 * version → drift). The client only maps it to presentation.
 */
export const RESCAN_META: Record<
  RescanReason,
  { icon: LucideIcon; label: (scannerVersion: string) => string; destructiveTone: boolean }
> = {
  retry: { icon: RefreshCw, label: () => "Retry", destructiveTone: true },
  partial: { icon: RefreshCw, label: () => "Rescan · incomplete", destructiveTone: false },
  version: { icon: ArrowUpCircle, label: (v) => `Rescan · v${v}`, destructiveTone: false },
  drift: { icon: GitCommit, label: () => "Rescan · docs changed", destructiveTone: false },
};
