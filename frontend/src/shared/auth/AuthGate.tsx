import { useLayoutEffect, type ReactNode } from "react";
import { AuthProvider, useAuth } from "react-oidc-context";
import { Loader2, LogIn, ShieldAlert } from "lucide-react";
import { OIDC, isConfigured } from "./config";
import { rolesFromToken } from "./roles";
import { bindSession } from "./session";
import { useI18n } from "../i18n";

/**
 * Sign-in, and nothing renders behind it.
 *
 * The panel has no useful anonymous state - every endpoint but `/health`
 * answers `401` - so this gates the whole app rather than each page. It also
 * binds the live session into `session.ts`, which is where `apiFetch` reads the
 * token from.
 *
 * `oidc-client-ts` owns the protocol: authorization code with PKCE, the code
 * verifier, and the silent renew that runs before expiry. What is ours is the
 * three states a user can be in while it works.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  if (!isConfigured()) return <NotConfigured />;
  return (
    <AuthProvider
      authority={OIDC.issuer}
      client_id={OIDC.clientId}
      redirect_uri={window.location.origin}
      post_logout_redirect_uri={window.location.origin}
      scope={OIDC.scope}
      /* Zitadel puts no profile claims in an access token, and none in the ID
         token either once an access token is issued (its endpoint docs say so
         explicitly). Without this the panel would greet everyone by their
         numeric subject: it fetches the userinfo endpoint after sign-in and
         merges `preferred_username` and friends into the profile. */
      loadUserInfo
      /* Renew before the token expires rather than after a request fails: a
         401 mid-session costs the user their place on the page. Which path it
         takes depends on the Zitadel application: with `offline_access` in the
         scope it refreshes with a refresh token, otherwise it opens a hidden
         iframe against this URI, which the application must therefore accept as
         a redirect. Both need the URI registered; neither needs a secret. */
      automaticSilentRenew
      silent_redirect_uri={window.location.origin}
      /* The authorization code stays in the URL after the redirect back, where
         it would be re-submitted on a refresh and rejected. */
      onSigninCallback={() =>
        window.history.replaceState({}, "", window.location.pathname)
      }
    >
      <SessionBoundary>{children}</SessionBoundary>
    </AuthProvider>
  );
}

function SessionBoundary({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const { t } = useI18n();

  /* A layout effect, not a passive one. React runs every layout effect before
     any passive effect, and a child's query fires from a passive effect - so
     with `useEffect` here the first request would leave before the token was
     bound, come back 401 and start a sign-in redirect. */
  useLayoutEffect(() => {
    bindSession({
      accessToken: () => auth.user?.access_token ?? null,
      /* A 401 from the API means this session is finished, whatever the
         library still believes. Sending the user through Zitadel is what
         resolves it - they come back signed in, or they do not come back. */
      unauthenticated: () => void auth.signinRedirect(),
    });
  }, [auth]);

  if (auth.activeNavigator || auth.isLoading) return <Waiting label={t("auth.signingIn")} />;

  if (auth.error) {
    return (
      <Notice icon={<ShieldAlert size={22} className="text-red-500" />} tone="red">
        <div className="mb-1 text-sm font-semibold text-red-800">{t("auth.failed")}</div>
        <div className="font-mono text-xs text-red-600">{auth.error.message}</div>
        <SignInButton onClick={() => void auth.signinRedirect()} label={t("auth.retry")} />
      </Notice>
    );
  }

  if (!auth.isAuthenticated) {
    return (
      <Notice icon={<LogIn size={22} className="text-gray-400" />} tone="gray">
        <div className="mb-1 text-sm font-semibold text-gray-700">{t("auth.required")}</div>
        <div className="mb-2 text-xs text-gray-500">{t("auth.requiredHint")}</div>
        <SignInButton onClick={() => void auth.signinRedirect()} label={t("auth.signIn")} />
      </Notice>
    );
  }

  /* Signed in to Zitadel, but holding no role on this project. The backend
     answers 401 to that token - the same status as an expired session - so
     letting the app render would send every query into a redirect back to a
     Zitadel that signs them in again: a loop with no exit and no explanation.
     Stopping here says what is wrong and offers the only thing that helps. */
  if (rolesFromToken(auth.user?.access_token).length === 0) {
    return (
      <Notice icon={<ShieldAlert size={22} className="text-amber-500" />} tone="amber">
        <div className="mb-1 text-sm font-semibold text-amber-900">{t("auth.noRole")}</div>
        <div className="mb-2 text-xs text-amber-800">{t("auth.noRoleHint")}</div>
        <SignInButton onClick={() => void auth.signoutRedirect()} label={t("auth.signOut")} />
      </Notice>
    );
  }

  return <>{children}</>;
}

function Waiting({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-24 text-sm text-gray-400">
      <Loader2 size={16} className="animate-spin" /> {label}
    </div>
  );
}

function Notice({
  icon,
  tone,
  children,
}: {
  icon: ReactNode;
  tone: "red" | "gray" | "amber";
  children: ReactNode;
}) {
  const border =
    tone === "red"
      ? "border-red-200 bg-red-50"
      : tone === "amber"
        ? "border-amber-200 bg-amber-50"
        : "border-gray-200 bg-white";
  return (
    <div className="mx-auto max-w-md px-6 py-24">
      <div className={`rounded-xl border p-8 text-center ${border}`}>
        <div className="mb-2 flex justify-center">{icon}</div>
        {children}
      </div>
    </div>
  );
}

function SignInButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mx-auto mt-3 flex items-center gap-1.5 rounded bg-brand px-3 py-1.5 text-xs font-semibold text-white transition hover:opacity-90"
    >
      <LogIn size={13} /> {label}
    </button>
  );
}

/** Shown instead of a sign-in button when nobody configured the issuer: an
 *  operator problem, and one no amount of clicking would fix. */
function NotConfigured() {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-md px-6 py-24">
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-center">
        <ShieldAlert size={22} className="mx-auto mb-2 text-amber-500" />
        <div className="mb-1 text-sm font-semibold text-amber-900">{t("auth.notConfigured")}</div>
        <div className="font-mono text-xs text-amber-800">{t("auth.notConfiguredHint")}</div>
      </div>
    </div>
  );
}
