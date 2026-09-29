import { Link } from "react-router";
import type { GenTarget } from "../data/types";
import type { Hold } from "../lib/layout";
import { useI18n } from "../../../shared/i18n";

/**
 * Why a resource cannot be generated on a target, in the card's words; an
 * unconfirmed layout also offers the way to the layout editor. Where the spec
 * is at hand, fields left to decide come after that (owner decision); away
 * from it, they come with the way to the spec, where they are highlighted
 * (owner decision). Nothing is said when nothing holds it.
 */
export function HoldReason({
  hold,
  open = 0,
  target,
  layoutTo,
  specTo,
  state,
}: {
  hold: Hold | null;
  /** Fields of the resource whose problem nobody has decided yet. */
  open?: number;
  target: GenTarget;
  layoutTo: string;
  /** The resource's spec, when the reason is shown away from it. */
  specTo?: string;
  state?: unknown;
}) {
  const { t } = useI18n();
  if (!hold) {
    if (open === 0) return null;
    const decide = t("gen.spec.decideFirst", { n: open });
    return specTo ? (
      <span className="inline-flex shrink-0 items-center gap-2 text-[11px] text-gray-400">
        {decide}
        <Link to={specTo} state={state} className="font-semibold text-brand underline">
          {t("gen.result.openSpec")}
        </Link>
      </span>
    ) : (
      <span className="text-[11px] text-gray-400">{decide}</span>
    );
  }
  const text = (() => {
    switch (hold.reason) {
      case "confirm":
        return t("gen.hold.confirm");
      case "empty":
        return t("gen.hold.empty");
      case "notOk":
        return t("gen.hold.notOk", { n: hold.n });
      case "waitsOn":
        return t("gen.waitsOn", { base: hold.base });
      case "notConnected":
        return t("gen.hold.notConnected", { target: target.label });
    }
  })();
  return (
    <span className="inline-flex shrink-0 items-center gap-2 text-[11px] text-gray-400">
      {text}
      {hold.reason === "confirm" && (
        <Link to={layoutTo} state={state} className="font-semibold text-brand underline">
          {t("gen.card.fixLayout")}
        </Link>
      )}
    </span>
  );
}
