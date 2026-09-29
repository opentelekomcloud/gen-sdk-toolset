import type { ReactNode } from "react";
import { useI18n } from "../../../shared/i18n";

/** A Generation page whose service or resource is not there: the way `back`, and nothing else. */
export function PageNotFound({ back }: { back: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-6xl px-6 py-5">
      {back}
      <div className="py-16 text-center text-sm text-gray-400">{t("app.notFound")}</div>
    </div>
  );
}
