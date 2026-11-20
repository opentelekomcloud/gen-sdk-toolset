import { retryJoining, type Retryable } from "../../scan/api/queries";
import { ServiceRetryCard } from "../../scan/components/ServicePageStates";
import { useI18n } from "../../../shared/i18n";

/**
 * A Generation page of a service when the targets came, but none of them: there
 * is nothing to generate for. That is an answer, not a failed load, and it is
 * said as such - never as a blank page. Retry asks for the targets again.
 */
export function NoTargets({ back, backState, targets }: { back: string; backState?: unknown; targets: Retryable }) {
  const { t } = useI18n();
  return (
    <ServiceRetryCard
      back={back}
      backState={backState}
      label={t("gen.noTargets")}
      onRetry={() => void retryJoining(targets)}
    />
  );
}
