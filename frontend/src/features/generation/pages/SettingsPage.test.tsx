import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router";
import { renderPage } from "../../../test/render";
import { tokenWithRoles } from "../../../test/token";
import { ApiError } from "../../scan/api/client";
import { Header } from "../../../components/Header";
import { otcSettings, resetGenerationMock, saveOtcSettings } from "../data/mock";
import type { OtcSettingsForm } from "../data/types";
import { SettingsPage } from "./SettingsPage";

/** The session the mocked provider hands back; each test sets the roles. */
const session = vi.hoisted(() => ({ token: "" }));

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: session.token, profile: { preferred_username: "ada@otc.test" } },
    isAuthenticated: true,
    isLoading: false,
    signinRedirect: vi.fn(),
    signoutRedirect: vi.fn(),
  }),
}));

/** What the mock does instead of answering: the mock itself never fails, a backend can. */
const fail = vi.hoisted(() => ({ load: false, save: null as Error | null }));

vi.mock("../data/mock", async (importOriginal) => {
  const mock = await importOriginal<typeof import("../data/mock")>();
  return {
    ...mock,
    otcSettings: () => {
      if (fail.load) throw new Error("settings store unavailable");
      return mock.otcSettings();
    },
    saveOtcSettings: vi.fn((form: OtcSettingsForm) => {
      if (fail.save) throw fail.save;
      mock.saveOtcSettings(form);
    }),
  };
});

/* The mock lives in module memory, and the saves below change it. */
beforeEach(() => {
  resetGenerationMock();
  vi.mocked(saveOtcSettings).mockClear();
  fail.load = false;
  fail.save = null;
  session.token = tokenWithRoles("worker");
});

function settingsPage() {
  return renderPage(<SettingsPage />, { path: "/settings", route: "/settings" });
}

const field = (label: string) => screen.getByLabelText(label);
const type = (label: string, value: string) => fireEvent.change(field(label), { target: { value } });
const DATE = /\d\d\/\d\d\/\d{4}, \d\d:\d\d/.source;

describe("the settings page: the OTC tenant only", () => {
  it("shows the stored tenant, and of its keys only that they are stored", async () => {
    settingsPage();

    expect(screen.getByRole("heading", { name: "Panel settings" })).toBeInTheDocument();
    expect(screen.getByText("Loading settings…")).toBeInTheDocument();
    expect(await screen.findByText("Open Telekom Cloud access")).toBeInTheDocument();
    expect(
      screen.getByText("Credentials are used server-side only — they never reach the browser again after saving."),
    ).toBeInTheDocument();
    expect(screen.getByText("used by Live check on the generation result screen")).toBeInTheDocument();
    expect(screen.getByText("credentials stored")).toBeInTheDocument();

    expect(field("Account (domain)")).toHaveValue("OTC00000000001000000042");
    expect(field("Account (domain)")).toHaveAttribute("type", "text");
    expect(screen.getByText("The OTC account the calls are billed to.")).toBeInTheDocument();
    expect(field("Tenant / project")).toHaveValue("eu-de_gen-sdk");
    expect(screen.getByText("Project the live calls run against.")).toBeInTheDocument();
    expect(field("Region")).toHaveValue("eu-de");
    expect(screen.getByText("Endpoint region for live calls.")).toBeInTheDocument();
    // the keys never come back: empty, hidden as typed, and marked stored
    for (const key of ["Access key (AK)", "Secret key (SK)"]) {
      expect(field(key)).toHaveValue("");
      expect(field(key)).toHaveAttribute("type", "password");
      expect(field(key)).toHaveAttribute("placeholder", "stored");
    }
    expect(screen.getByText("Write-only — the panel shows it as stored, never as text.")).toBeInTheDocument();
    expect(screen.queryByText(/AKSTORED|SKSTORED/)).toBeNull();
    expect(screen.queryByDisplayValue(/STORED/)).toBeNull();

    // GitHub stays configured from the environment (owner decision)
    expect(screen.queryByText(/GitHub|token|repository|organisation/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Save settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Test connection" })).toBeInTheDocument();
  });

  it("saves what was typed, keeps the stored key left empty, and says when", async () => {
    settingsPage();

    await screen.findByText("Open Telekom Cloud access");
    type("Tenant / project", "eu-nl_gen-sdk");
    type("Region", "eu-nl");
    type("Secret key (SK)", "SKNEW0001");
    expect(field("Secret key (SK)")).toHaveValue("SKNEW0001");
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    expect(await screen.findByText(new RegExp(`^Saved · ${DATE}$`))).toBeInTheDocument();
    expect(saveOtcSettings).toHaveBeenCalledWith({
      account: "OTC00000000001000000042",
      tenant: "eu-nl_gen-sdk",
      region: "eu-nl",
      ak: "",
      sk: "SKNEW0001",
    });
    expect(otcSettings()).toEqual({
      account: "OTC00000000001000000042",
      tenant: "eu-nl_gen-sdk",
      region: "eu-nl",
      akStored: true,
      skStored: true,
    });
    // the form shows what is stored now; the key typed is gone from the page again
    expect(field("Tenant / project")).toHaveValue("eu-nl_gen-sdk");
    expect(field("Region")).toHaveValue("eu-nl");
    expect(field("Secret key (SK)")).toHaveValue("");
    expect(field("Secret key (SK)")).toHaveAttribute("placeholder", "stored");
    expect(screen.getByText("credentials stored")).toBeInTheDocument();

    // the next edit takes the note away, as in the prototype
    type("Account (domain)", "OTC00000000001000000043");
    expect(screen.queryByText(/^Saved ·/)).toBeNull();
  });

  it("calls the settings incomplete once the tenant saved is empty", async () => {
    settingsPage();

    await screen.findByText("Open Telekom Cloud access");
    type("Tenant / project", "");
    // not before it is saved: the state is the stored settings'
    expect(screen.getByText("credentials stored")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    expect(await screen.findByText("incomplete")).toBeInTheDocument();
    expect(screen.queryByText("credentials stored")).toBeNull();
    expect(field("Tenant / project")).toHaveValue("");
    expect(field("Tenant / project")).toHaveAttribute("placeholder", "eu-de_gen-sdk");
  });

  it("tests the tenant as the form has it, and saves nothing", async () => {
    settingsPage();

    await screen.findByText("Open Telekom Cloud access");
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText("OTC ok (eu-de)")).toBeInTheDocument();

    type("Tenant / project", "");
    expect(screen.queryByText("OTC ok (eu-de)")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText("OTC: AK/SK or tenant missing")).toBeInTheDocument();

    type("Tenant / project", "eu-nl_gen-sdk");
    type("Region", "eu-nl");
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText("OTC ok (eu-nl)")).toBeInTheDocument();
    expect(saveOtcSettings).not.toHaveBeenCalled();
    expect(otcSettings()).toMatchObject({ tenant: "eu-de_gen-sdk", region: "eu-de" });
  });

  it("shows a refused save, and keeps what was typed", async () => {
    fail.save = new ApiError(403, "forbidden", "worker role required");
    settingsPage();

    await screen.findByText("Open Telekom Cloud access");
    type("Tenant / project", "eu-nl_gen-sdk");
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    expect(await screen.findByText("Your role does not allow that")).toBeInTheDocument();
    expect(screen.getByText("worker role required")).toBeInTheDocument();
    expect(screen.queryByText(/^Saved ·/)).toBeNull();
    expect(field("Tenant / project")).toHaveValue("eu-nl_gen-sdk");
    expect(otcSettings()).toMatchObject({ tenant: "eu-de_gen-sdk" });

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(screen.queryByText("Your role does not allow that")).toBeNull());
  });

  it("says the settings did not load, and loads them again on retry", async () => {
    fail.load = true;
    settingsPage();

    expect(await screen.findByText("Failed to load settings")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save settings" })).toBeNull();

    fail.load = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Open Telekom Cloud access")).toBeInTheDocument();
    expect(field("Tenant / project")).toHaveValue("eu-de_gen-sdk");
  });
});

describe("the settings page for a viewer", () => {
  it("shows the settings read-only, without saving, and still offers the test", async () => {
    session.token = tokenWithRoles("viewer");
    settingsPage();

    expect(await screen.findByText("credentials stored")).toBeInTheDocument();
    expect(field("Tenant / project")).toHaveValue("eu-de_gen-sdk");
    for (const label of ["Account (domain)", "Tenant / project", "Region", "Access key (AK)", "Secret key (SK)"]) {
      expect(field(label)).toHaveAttribute("readonly");
    }
    expect(screen.queryByRole("button", { name: "Save settings" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText("OTC ok (eu-de)")).toBeInTheDocument();
  });
});

/** Where the panel navigated to. */
function Location() {
  const { pathname } = useLocation();
  return <output data-testid="location">{pathname}</output>;
}

describe("the way to the settings", () => {
  it("is the gear in the header, lit while the settings are open", async () => {
    renderPage(
      <>
        <Header />
        <Routes>
          <Route path="scan" element={<div>scan registry</div>} />
          <Route path="settings" element={<SettingsPage />} />
        </Routes>
        <Location />
      </>,
      { path: "/scan", route: "*" },
    );

    const gear = screen.getByRole("link", { name: "Panel settings" });
    expect(gear).toHaveAttribute("href", "/settings");
    expect(gear).toHaveAttribute("title", "Panel settings");
    expect(gear).not.toHaveAttribute("aria-current");
    expect(screen.getByText("scan registry")).toBeInTheDocument();

    fireEvent.click(gear);
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/settings"));
    expect(screen.getByRole("link", { name: "Panel settings" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("Open Telekom Cloud access")).toBeInTheDocument();
  });
});
