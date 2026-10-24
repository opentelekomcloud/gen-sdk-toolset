import { ODSLoadingSpinner } from "@telekom-ods/react-ui-kit/ODSLoadingSpinner";

/**
 * The ODS spinner at icon size, for "something is running" next to text that
 * already says what. It is hidden from assistive tech for that reason: the
 * ODS component announces its own "Loading", which would only repeat the text.
 */
export function Spinner({ className = "" }: { className?: string }) {
  return <ODSLoadingSpinner size="xSmall" aria-hidden="true" className={`inline-flex shrink-0 ${className}`} />;
}
