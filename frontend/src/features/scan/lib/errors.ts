import { ApiError } from "../api/client";
import type { MessageKey } from "../../../shared/i18n";

/**
 * Registry rows have one line for a failure, next to the rescan button. The
 * full message names the repository, the ref and the provider's own wording,
 * which does not fit and pushes the button out of the row.
 *
 * The leading clause is what a reader scans for ("Could not resolve commit",
 * "Failed to fetch document content"); everything after the first " for " or
 * ":" is detail. Nothing is lost - callers keep the full text in the title
 * attribute, and the service page shows it in full.
 */
export function shortError(message: string): string {
  const cut = Math.min(
    ...[message.indexOf(" for "), message.indexOf(":")]
      .filter((index) => index > 0)
      .concat(message.length),
  );
  return message.slice(0, cut).trim();
}

/**
 * Why activating a snapshot was refused. The two the server answers on purpose
 * — a scan holding the pointer, a snapshot that is gone — get their own line;
 * anything else keeps the generic one and shows the server's own message.
 */
export function activationErrorKey(error: unknown): MessageKey {
  if (error instanceof ApiError && error.status === 403) return "auth.forbidden";
  if (error instanceof ApiError && error.status === 409) return "snap.activateConflict";
  if (error instanceof ApiError && error.status === 404) return "snap.activateGone";
  return "snap.activateFailed";
}

/**
 * Why a state-changing request was refused. `403` is the one the UI is supposed
 * to prevent by hiding the control, which is exactly why it needs a line of its
 * own: reaching it means the page was showing something the session may not do,
 * and "could not do that" would leave the user clicking it again.
 */
export function mutationErrorKey(error: unknown): MessageKey {
  if (error instanceof ApiError && error.status === 403) return "auth.forbidden";
  if (error instanceof ApiError && error.status === 409) return "mutation.conflict";
  return "mutation.failed";
}
