import type { ReactNode } from "react";
import { useI18n } from "../../../shared/i18n";
import { PageMessage } from "./PageMessage";

/** A Generation page whose service or resource is not there: the way `back`, and nothing else. */
export function PageNotFound({ back }: { back: ReactNode }) {
  const { t } = useI18n();
  return <PageMessage back={back} note={t("app.notFound")} />;
}
