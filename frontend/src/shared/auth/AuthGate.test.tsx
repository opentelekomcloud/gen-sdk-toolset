import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { I18nProvider } from "../i18n";
import { tokenWithRoles } from "../../test/token";

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
