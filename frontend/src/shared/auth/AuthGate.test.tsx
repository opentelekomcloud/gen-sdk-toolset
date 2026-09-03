import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { I18nProvider } from "../i18n";
import { tokenWithRoles } from "../../test/token";
import { apiFetch } from "../../features/scan/api/client";
import { resetSession } from "./session";

/** What the mocked provider hands back; each test sets the token. */
const session = vi.hoisted(() => ({ token: "", signOut: vi.fn() }));

/* `config.ts` reads import.meta.env once, at module load, because Vite inlines
   those values at build time - so a stubbed env after the import would change
   nothing. Mocked through getters instead, which keeps production code the
   shape production needs. */
const config = vi.hoisted(() => ({ issuer: "https://panel.zitadel.test", clientId: "123@panel" }));

vi.mock("./config", () => ({
  OIDC: {
    get issuer() {
      return config.issuer;
    },
    get clientId() {
      return config.clientId;
    },
    scope: "openid profile email",
  },
  isConfigured: () => Boolean(config.issuer && config.clientId),
}));

vi.mock("react-oidc-context", () => ({
  AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  useAuth: () => ({
    user: { access_token: session.token, profile: { preferred_username: "ada@otc.test" } },
    isAuthenticated: true,
    isLoading: false,
    activeNavigator: undefined,
    error: undefined,
    signinRedirect: vi.fn(),
    signoutRedirect: session.signOut,
  }),
}));

import { AuthGate } from "./AuthGate";

function gate() {
  return render(
    <I18nProvider>
      <AuthGate>
        <div>the panel</div>
      </AuthGate>
    </I18nProvider>,
  );
}

beforeEach(() => {
  config.issuer = "https://panel.zitadel.test";
  config.clientId = "123@panel";
  session.signOut.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetSession();
});

describe("AuthGate", () => {
  it("shows the panel to a session that holds a role", () => {
    session.token = tokenWithRoles("viewer");

    gate();

    expect(screen.getByText("the panel")).toBeInTheDocument();
  });

  it("stops a session with no panel role instead of letting it loop", () => {
    /* The backend answers 401 to this token, and apiFetch turns a 401 into a
       sign-in redirect - which Zitadel would satisfy instantly, returning the
       same role-less token. Rendering the panel here is what would make that a
       loop, so the gate refuses and says why. */
    session.token = tokenWithRoles();

    gate();

    expect(screen.queryByText("the panel")).toBeNull();
    expect(screen.getByText(/no access to this panel/i)).toBeInTheDocument();
  });

  it("offers the role-less session the only move that helps: signing out", () => {
    session.token = tokenWithRoles();

    gate();
    screen.getByRole("button", { name: /sign out/i }).click();

    expect(session.signOut).toHaveBeenCalledOnce();
  });

  it("says so when nobody configured the issuer, rather than offering a dead button", () => {
    config.issuer = "";
    session.token = tokenWithRoles("worker");

    gate();

    expect(screen.getByText(/not configured/i)).toBeInTheDocument();
    expect(screen.queryByText("the panel")).toBeNull();
  });
});

describe("the session is bound before the app can use it", () => {
  /** A child that requests on mount - which is what every page's query does. */
  function RequestsOnMount() {
    useEffect(() => {
      void apiFetch("/scan/summary").catch(() => undefined);
    }, []);
    return <div>the panel</div>;
  }

  it("carries the token on the very first request", async () => {
    /* The binding has to happen in a layout effect: React runs those before any
       passive effect, and this child fetches from a passive one. Bound too late
       and the first request goes out bare, is refused, and starts a redirect
       loop on a session that was perfectly good. */
    const spy = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", spy);
    session.token = tokenWithRoles("worker");

    render(
      <I18nProvider>
        <AuthGate>
          <RequestsOnMount />
        </AuthGate>
      </I18nProvider>,
    );

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const [, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      `Bearer ${session.token}`,
    );
  });
});
