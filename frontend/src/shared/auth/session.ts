/**
 * What `apiFetch` needs to know about the signed-in user, without importing
 * React to find it out.
 *
 * The OIDC session lives in a React context, but the API client is a plain
 * function called from query functions all over the feature. Threading a token
 * through every one of them would put authentication in the signature of code
 * that has nothing to do with it, so the session registers itself here once and
 * the client reads it. That makes this module the one piece of global state in
 * the frontend, which is why it is this small: two values, set from one place.
 */

type TokenReader = () => string | null;

let readToken: TokenReader = () => null;
let onUnauthenticated: () => void = () => {};
let redirecting = false;

/**
 * Point the API client at the live session. Called by `AuthGate` whenever the
 * user changes - including at sign-out, when the reader starts returning null.
 */
export function bindSession(options: {
  accessToken: TokenReader;
  unauthenticated: () => void;
}): void {
  readToken = options.accessToken;
  onUnauthenticated = options.unauthenticated;
  redirecting = false;
}

/** The bearer token for the next request, or null while nobody is signed in. */
export function accessToken(): string | null {
  return readToken();
}

/**
 * Report that the API refused the session.
 *
 * The token may be valid and simply unknown to this panel, or the clock may
 * have moved past an expiry the silent renew did not catch. Either way the
 * session is over, and the handler sends the user back to Zitadel.
 */
export function sessionExpired(): void {
  /* A page holds several queries and they fail together: without this the first
     refusal starts a redirect and the rest pile on behind it. */
  if (redirecting) return;
  redirecting = true;
  onUnauthenticated();
}

/** Drop the binding. Only tests need this; the app binds once and rebinds. */
export function resetSession(): void {
  readToken = () => null;
  onUnauthenticated = () => {};
  redirecting = false;
}
