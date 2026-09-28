import type { GenOrigin, GenResource } from "../data/types";
import { useI18n, type MessageKey } from "../../../shared/i18n";

/** Where a resource stands in the layout: confirmed, or where it came from. */
type Badge = GenOrigin | "confirmed";

const BADGE_CLS: Record<Badge, string> = {
  auto: "border-gray-200 bg-gray-100 text-gray-500",
  confirmed: "border-emerald-200 bg-emerald-50 text-emerald-700",
  new: "border-blue-200 bg-blue-50 text-blue-700",
};

/** A resource's layout badge: `confirmed` once someone has confirmed it, its origin until then. */
export function LayoutBadge({ resource }: { resource: Pick<GenResource, "confirmedBy" | "origin"> }) {
  const { t } = useI18n();
  const badge: Badge = resource.confirmedBy != null ? "confirmed" : resource.origin;
  return (
    <span className={`rounded-full border px-2 py-px text-[10px] font-semibold uppercase tracking-wide ${BADGE_CLS[badge]}`}>
      {t(`gen.layout.origin.${badge}` as MessageKey)}
    </span>
  );
}
