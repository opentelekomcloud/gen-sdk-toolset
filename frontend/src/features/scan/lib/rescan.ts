import { ODSCircleArrowUp, ODSEdit, ODSRefresh } from "@telekom-ods/react-icons";
import type { IconComponent } from "../../../shared/ui/icon";
import type { RescanReason } from "../../../shared/api/types";
import type { MessageKey } from "../../../shared/i18n";

/**
 * rescan_reason is computed SERVER-side (PS2, priority retry → version → drift).
 * The client only maps it to presentation; labels are i18n keys (rescan.* —
 * `rescan.version` interpolates {v}). Keyed by the generated union, so a reason
 * the backend adds or drops breaks this map rather than passing unnoticed.
 */
export const RESCAN_META: Record<RescanReason, { icon: IconComponent; labelKey: MessageKey; destructiveTone: boolean }> = {
  retry: { icon: ODSRefresh, labelKey: "rescan.retry", destructiveTone: true },
  version: { icon: ODSCircleArrowUp, labelKey: "rescan.version", destructiveTone: false },
  drift: { icon: ODSEdit, labelKey: "rescan.drift", destructiveTone: false },
};
