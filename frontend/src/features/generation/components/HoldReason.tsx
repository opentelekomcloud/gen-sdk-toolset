import { Link } from "react-router";
import type { GenTarget } from "../data/types";
import type { Hold } from "../lib/layout";
import { useI18n } from "../../../shared/i18n";

/**
 * Why a resource cannot be generated on a target, in the card's words; an
 * unconfirmed layout also offers the way to the layout editor.
 */
export function HoldReason({
  hold,
  target,
  layoutTo,
  state,
}: {
  hold: Hold;
  target: GenTarget;
  layoutTo: string;
  state?: unknown;
}) {
  const { t } = useI18n();
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
