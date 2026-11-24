import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Link, Route, Routes, useLocation } from "react-router";
import {
  alertNamed,
  backend,
  CONFLICT,
  FAILED,
  FORBIDDEN,
  later,
  NOT_FOUND,
  pollAgain,
  refresh,
  renderPage,
} from "../../../test/render";
import { mockFails } from "../../../test/mockFails";
import { endpoint, generationList, layout } from "../../../test/fixtures";
import { expectRetryJoinsResources } from "../../../test/generationMock";
import { tokenWithRoles } from "../../../test/token";
import { keys } from "../../scan/api/queries";
import { generationResources, generationTargets, resetGenerationMock } from "../data/mock";
import type { Layout, LayoutResource } from "../../../shared/api/types";
import { GenerationLayoutPage } from "./GenerationLayoutPage";
import { GenerationListPage } from "./GenerationListPage";
import { GenerationServicePage } from "./GenerationServicePage";

/** The session the mocked provider hands back; each test sets the roles. */
const session = vi.hoisted(() => ({ token: "" }));

/* The flags as the panel ships them, unless a test switches one on. */
const flags = vi.hoisted(() => ({ showGenJobs: false, showLayoutOrigin: false }));
vi.mock("../flags", () => ({
  SHOW_GEN_STATE: false,
  SHOW_GEN_RESULT: false,
  get SHOW_GEN_JOBS() {
    return flags.showGenJobs;
  },
  get SHOW_LAYOUT_ORIGIN() {
    return flags.showLayoutOrigin;
  },
}));

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: session.token, profile: { preferred_username: "ada@otc.test" } },
    isAuthenticated: true,
    isLoading: false,
    signinRedirect: vi.fn(),
    signoutRedirect: vi.fn(),
  }),
}));

/* The mock's targets and resources, behind the switches some tests set (`mockFails`). */
vi.mock("../data/mock", async (importOriginal) =>
  (await import("../../../test/mockFails")).withMockFails(await importOriginal<typeof import("../data/mock")>()),
);

beforeEach(() => {
  resetGenerationMock();
  flags.showGenJobs = false;
  flags.showLayoutOrigin = false;
  session.token = tokenWithRoles("worker");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LIST = "/api/generation/services";
const LAYOUT = "/api/generation/services/billing-api/layout";
const ADD = `${LAYOUT}/resources`;
const rename = (id: number) => `${LAYOUT}/resources/${id}/rename`;
const MOVE = `${LAYOUT}/endpoints/move`;

const unconfirmed = { confirmed_by: null, confirmed_at: null };

const LIST_INVOICES = endpoint({
  id: 1,
  path: "invoices/list-invoices.rst",
  title: "List invoices of a project",
  uri: "/v1/billing/invoices",
});
const SHOW_INVOICE = endpoint({
  id: 2,
  path: "invoices/show-invoice.rst",
  title: "Query invoice details",
  uri: "/v1/billing/invoices/{invoice_id}",
});
const LIST_PAYMENTS = endpoint({ id: 3, path: "payments/list-payments.rst", title: "List payments", uri: "/v1/billing/payments" });
const QUOTAS = endpoint({
  id: 4,
  path: "quotas/show-quotas.rst",
  title: "Query billing quotas",
  uri: "/v1/billing/quotas",
  overall_status: "partial",
});
const EXPORT_V2 = endpoint({
  id: 5,
  path: "v2/invoices/export-invoices.rst",
  title: "Export invoices as CSV",
  method: "POST",
  uri: "/v2/billing/invoices/export",
});
/* In no resource of v1: its URI has no constant segment after the version. */
const HEALTH = endpoint({ id: 6, path: "health/check.rst", title: "Check the service", uri: "/v1" });
/* With no version: the scanner found none. */
const VERSIONS = endpoint({ id: 7, path: "versions/list-versions.rst", title: "List API versions", uri: "/" });

const INVOICES: LayoutResource = {
  id: 1,
  name: "invoices",
  confirmed_by: "valeriia",
  confirmed_at: "2026-08-11T13:58:00Z",
  endpoints: [LIST_INVOICES, SHOW_INVOICE],
};
const PAYMENTS: LayoutResource = { id: 2, name: "payments", ...unconfirmed, endpoints: [LIST_PAYMENTS] };
const MISC: LayoutResource = { id: 3, name: "misc", ...unconfirmed, endpoints: [QUOTAS] };
const INVOICES_V2: LayoutResource = { id: 4, name: "invoices", ...unconfirmed, endpoints: [EXPORT_V2] };

/** billing-api as the server stores it: two versions, v1 with an endpoint in no resource, and one endpoint with no version. */
function billing({
  v1 = [INVOICES, PAYMENTS, MISC],
  v2 = [INVOICES_V2],
  unassigned = [HEALTH],
  noVersion = [VERSIONS],
}: { v1?: LayoutResource[]; v2?: LayoutResource[]; unassigned?: typeof HEALTH[]; noVersion?: typeof HEALTH[] } = {}): Layout {
  return layout({
    versions: [
      { api_version: "v1", resources: v1, unassigned },
      { api_version: "v2", resources: v2, unassigned: [] },
    ],
    no_version: noVersion,
  });
}

/** Where the page navigated to. */
function Location() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}

/**
 * The layout page of billing-api on a backend that lists it and stores
 * `billing()`; `answers` adds to that or replaces it, and stays the test's to
 * change - the backend answers what it holds at the moment of each request.
 * `seed` holds what the mock would answer otherwise.
 */
function editor(
  answers: Record<string, unknown> = {},
  path = "/generation/billing-api/layout",
  seed: [readonly unknown[], unknown][] = [],
) {
  const all: Record<string, unknown> = { [LIST]: generationList("billing-api"), [LAYOUT]: billing(), ...answers };
  const api = backend(all);
  const rendered = renderPage(
    <>
      <GenerationLayoutPage />
      <Location />
    </>,
    { path, route: "/generation/:name/layout", seed },
  );
  return { ...rendered, api, answers: all };
}

const version = (id: string) => screen.getByRole("region", { name: id });
const resource = (versionId: string, name: string) => within(version(versionId)).getByRole("group", { name });
/** An endpoint's row, by its document's title. */
const endpointRow = (title: string) => screen.getByText(title).closest("[draggable]") as HTMLElement;
const button = (scope: HTMLElement, name: string | RegExp) => within(scope).getByRole("button", { name });
const nameField = (label = "Rename resource") => screen.getByRole("textbox", { name: label });

/** Drag an endpoint onto a resource or a list, as the browser fires it. */
function dragTo(title: string, target: HTMLElement) {
  fireEvent.dragStart(endpointRow(title));
  fireEvent.dragOver(target);
  fireEvent.drop(target);
}

/** Let a request the page might have sent go out and come back. */
const settle = () => act(async () => {});

describe("the stored layout in the editor (ISS-0042)", () => {
  it("shows every version with its resources and endpoints, the unassigned and no version lists, the summary and the way back", async () => {
    editor();

    expect(screen.getByText("Loading service…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();
    expect(screen.getByText("needs confirmation")).toBeInTheDocument();
    // every endpoint counts: in a resource, unassigned, or with no version
    expect(
      screen.getByText("Shared layout · 2 versions · 4 resources · 7 endpoints · 1 of 4 resources confirmed"),
    ).toBeInTheDocument();
    // a version counts its unassigned endpoints too, as the summary does
    expect(within(version("v1")).getByText("3 resources · 5 endpoints")).toBeInTheDocument();
    expect(within(version("v2")).getByText("1 resource · 1 endpoint")).toBeInTheDocument();

    const invoices = resource("v1", "invoices");
    expect(within(invoices).getByText("2 endpoints")).toBeInTheDocument();
    expect(within(invoices).getByText("List invoices of a project")).toBeInTheDocument();
    expect(within(invoices).getByText("Query invoice details")).toBeInTheDocument();
    expect(resource("v2", "invoices")).toBeInTheDocument();

    const quotas = endpointRow("Query billing quotas");
    expect(within(quotas).getByText("GET")).toBeInTheDocument();
    expect(within(quotas).getByText("/v1/billing/quotas")).toBeInTheDocument();
    expect(within(quotas).getByText("partial")).toHaveAttribute(
      "title",
      "Not recognized in full — a resource holding this endpoint cannot be generated. It can be dragged to another resource.",
    );
    expect(within(resource("v1", "misc")).getByText("Query billing quotas")).toBeInTheDocument();

    const unassigned = within(version("v1")).getByRole("group", { name: "Unassigned" });
    expect(within(unassigned).getByText("Check the service")).toBeInTheDocument();
    expect(within(unassigned).getByText("In no resource yet — drag each into a resource of v1.")).toBeInTheDocument();
    // v2 has nothing unassigned
    expect(within(version("v2")).queryByRole("group", { name: "Unassigned" })).toBeNull();

    const noVersion = screen.getByRole("region", { name: "No version" });
    expect(within(noVersion).getByText("List API versions")).toBeInTheDocument();
    expect(
      within(noVersion).getByText(
        "The scanner found no API version for these — drag each into a resource of the version it belongs to.",
      ),
    ).toBeInTheDocument();

    const back = screen.getAllByRole("link", { name: "Back to generation" });
    expect(back).toHaveLength(2);
    for (const link of back) expect(link).toHaveAttribute("href", "/generation/billing-api");
    expect(screen.queryByText("Changes saved on the service")).toBeNull();
  });

  it("shows each resource's confirmation from confirmed_by and confirmed_at, and offers no Confirm for a confirmed one", async () => {
    editor();

    const invoices = await within(await screen.findByRole("region", { name: "v1" })).findByRole("group", { name: "invoices" });
    expect(within(invoices).getByText("confirmed")).toBeInTheDocument();
    expect(within(invoices).getByText(/^confirmed by valeriia · \d\d\/\d\d\/2026, \d\d:\d\d$/)).toBeInTheDocument();
    expect(within(resource("v1", "payments")).getByText("layout not confirmed yet")).toBeInTheDocument();
    expect(within(resource("v1", "payments")).queryByText("confirmed")).toBeNull();
    expect(within(invoices).queryByRole("button", { name: "Confirm layout" })).toBeNull();
    expect(button(resource("v1", "payments"), "Confirm layout")).toBeEnabled();
    // a Confirm for each resource only: none for a version or the whole layout (ADR-0066)
    expect(screen.getAllByRole("button", { name: "Confirm layout" })).toHaveLength(3);
    expect(within(version("v1")).getAllByRole("button", { name: "Confirm layout" })).toHaveLength(2);
    expect(screen.getByText(/once confirmed, each edition inherits it/)).toBeInTheDocument();
  });

  it("says the layout is confirmed once every resource is", async () => {
    editor({ [LAYOUT]: billing({ v1: [INVOICES], v2: [{ ...INVOICES_V2, confirmed_by: "ivan", confirmed_at: "2026-08-12T08:00:00Z" }] }) });

    expect(await screen.findByText("layout confirmed")).toBeInTheDocument();
    expect(screen.getByText(/· 2 of 2 resources confirmed$/)).toBeInTheDocument();
  });

  it("shows none of what the stored layout does not hold: no origin, no job, nothing hidden", async () => {
    // the mock has billing-api's invoices in review on Python SDK, and its names as auto or new
    editor();

    await screen.findByRole("region", { name: "v1" });
    await settle();
    // the mock is not even asked
    expect(mockFails.resourceCalls).toBe(0);
    expect(screen.queryByText("auto")).toBeNull();
    expect(screen.queryByText("new")).toBeNull();
    expect(screen.queryByText(/in review/)).toBeNull();
    expect(button(resource("v1", "invoices"), "Rename resource")).toBeInTheDocument();
    expect(endpointRow("List invoices of a project")).toHaveAttribute("draggable", "true");
  });

  it("names an endpoint without a title by its document's path, and one without a method or URI with a dash", async () => {
    const bare = endpoint({ id: 8, path: "misc/undocumented.rst", title: null, method: null, uri: null });
    editor({ [LAYOUT]: billing({ noVersion: [bare] }) });

    await screen.findByText("misc/undocumented.rst");
    const row = endpointRow("misc/undocumented.rst");
    expect(within(row).getAllByText("—")).toHaveLength(2);
  });

  it("shows a document status the panel has no words for as the backend sends it", async () => {
    const odd = endpoint({ id: 8, path: "odd.rst", title: "An odd document", overall_status: "skipped" });
    editor({ [LAYOUT]: billing({ v2: [{ ...INVOICES_V2, endpoints: [EXPORT_V2, odd] }] }) });

    await screen.findByText("An odd document");
    expect(within(endpointRow("An odd document")).getByText("skipped")).toHaveAttribute(
      "title",
      "Not recognized in full — a resource holding this endpoint cannot be generated. It can be dragged to another resource.",
    );
  });

  it("says a layout that holds nothing so, rather than showing an empty page", async () => {
    editor({ [LAYOUT]: layout({ versions: [], no_version: [] }) });

    expect(await screen.findByText("Nothing laid out for this service yet.")).toBeInTheDocument();
    // nothing is confirmed of a layout of no resources, and "0 of 0" is not said
    expect(screen.getByText("Shared layout · 0 versions · 0 resources · 0 endpoints")).toBeInTheDocument();
    expect(screen.getByText("needs confirmation")).toBeInTheDocument();
  });

  it("folds a version and a resource", async () => {
    editor();
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "payments"), "payments"));
    expect(screen.queryByText("List payments")).toBeNull();
    expect(screen.getByText("Query billing quotas")).toBeInTheDocument();

    fireEvent.click(button(version("v1"), "v1"));
    expect(within(version("v1")).queryByRole("group")).toBeNull();
    expect(within(version("v2")).getByRole("group", { name: "invoices" })).toBeInTheDocument();
  });

  it("keeps a version open while a name is typed in it, so its field is never folded away", async () => {
    editor();
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    expect(button(version("v1"), "v1")).toBeDisabled();
    fireEvent.click(button(version("v1"), "v1"));
    expect(nameField()).toHaveValue("charges");
    // another version still folds
    fireEvent.click(button(version("v2"), "v2"));
    expect(within(version("v2")).queryByRole("group")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(button(version("v1"), "v1")).toBeEnabled();
  });

  it("opens a folded version to ask for a new resource there, and folds it again once the name is dropped", async () => {
    editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(version("v1"), "v1"));
    expect(within(version("v1")).queryByRole("group")).toBeNull();

    fireEvent.click(button(version("v1"), "New resource"));

    expect(nameField("Name of the new resource")).toBeVisible();
    expect(button(version("v1"), "v1")).toHaveAttribute("aria-expanded", "true");
    expect(button(version("v1"), "v1")).toBeDisabled();

    fireEvent.keyDown(nameField("Name of the new resource"), { key: "Escape" });

    expect(within(version("v1")).queryByRole("group")).toBeNull();
    expect(button(version("v1"), "v1")).toHaveAttribute("aria-expanded", "false");
  });

  it("offers no reset of a resource or of a version: nothing goes back to the grouping (ADR-0064)", async () => {
    editor();
    await screen.findByRole("region", { name: "v1" });

    expect(screen.queryByRole("button", { name: /Reset/ })).toBeNull();
    expect(screen.queryByTitle(/Reset/)).toBeNull();
  });
});

describe("renaming a resource", () => {
  it("renames it on the server and shows the layout the server answered with, without reading it again", async () => {
    const renamed = billing({ v1: [INVOICES, { ...PAYMENTS, name: "charges" }, MISC] });
    const { api, client } = editor({ [rename(2)]: renamed });
    await screen.findByRole("region", { name: "v1" });
    const reads = api.calls(LAYOUT);

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    expect(nameField()).toHaveValue("payments");
    fireEvent.change(nameField(), { target: { value: " charges " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await within(version("v1")).findByRole("group", { name: "charges" })).toBeInTheDocument();
    expect(api.sent(rename(2))).toEqual([{ name: "charges" }]);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(within(version("v1")).queryByRole("group", { name: "payments" })).toBeNull();
    expect(screen.getByText("Changes saved on the service")).toBeInTheDocument();
    expect(api.calls(LAYOUT)).toBe(reads);
    // the edit is kept for that note, without a copy of the layout
    const kept = client.getMutationCache().getAll();
    expect(kept.map((m) => m.state.status)).toEqual(["success"]);
    expect(kept[0].state.data).toBeUndefined();
  });

  it("drops the confirmation the server dropped on a rename (ADR-0068)", async () => {
    const renamed = billing({ v1: [{ ...INVOICES, name: "bills", ...unconfirmed }, PAYMENTS, MISC] });
    editor({ [rename(1)]: renamed });
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "invoices"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "bills" } });
    fireEvent.keyDown(nameField(), { key: "Enter" });

    const bills = await within(version("v1")).findByRole("group", { name: "bills" });
    expect(within(bills).getByText("layout not confirmed yet")).toBeInTheDocument();
  });

  it("refuses a name that is not a package name, before anything goes out (ADR-0065)", async () => {
    const { api } = editor();
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    for (const name of ["Charges", "1charges", "char-ges", ""]) {
      fireEvent.change(nameField(), { target: { value: name } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      expect(
        screen.getByText("Package name: lowercase latin, digits and underscores, starting with a letter."),
      ).toBeInTheDocument();
    }
    // typing clears it
    fireEvent.change(nameField(), { target: { value: "charge" } });
    expect(screen.queryByText(/^Package name/)).toBeNull();
    await settle();
    expect(api.sent(rename(2))).toEqual([]);
  });

  it("refuses a name its version already has, and takes one only another version has (ADR-0065)", async () => {
    const { api } = editor({ [rename(4)]: billing({ v2: [{ ...INVOICES_V2, name: "payments" }] }) });
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "misc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText("A resource with this name already exists in v1.")).toBeInTheDocument();
    await settle();
    expect(api.sent(rename(2))).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    // payments is v1's: v2 may have one too
    fireEvent.click(button(resource("v2", "invoices"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "payments" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await within(version("v2")).findByRole("group", { name: "payments" })).toBeInTheDocument();
    expect(api.sent(rename(4))).toEqual([{ name: "payments" }]);
  });

  it("sends nothing for the name it already has, and drops a rename on Escape or Cancel", async () => {
    const { api } = editor();
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.queryByRole("textbox")).toBeNull();

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    fireEvent.keyDown(nameField(), { key: "Escape" });
    expect(screen.queryByRole("textbox")).toBeNull();

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("textbox")).toBeNull();

    await settle();
    expect(api.calls(rename(2))).toBe(0);
    expect(resource("v1", "payments")).toBeInTheDocument();
  });

  it("sends one rename while it is under way, however often it is saved", async () => {
    const answer = later();
    const { api } = editor({ [rename(2)]: answer.arrived });
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeDisabled());
    // the answer closes the field: nothing typed after Save would be kept
    expect(nameField()).toHaveAttribute("readonly");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    fireEvent.keyDown(nameField(), { key: "Enter" });

    answer.send(billing({ v1: [INVOICES, { ...PAYMENTS, name: "charges" }, MISC] }));

    expect(await within(version("v1")).findByRole("group", { name: "charges" })).toBeInTheDocument();
    expect(api.calls(rename(2))).toBe(1);
  });

  it("opens no other name field while a save is under way, so its answer closes only its own", async () => {
    const answer = later();
    editor({ [rename(2)]: answer.arrived });
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(button(resource("v1", "misc"), "Rename resource")).toBeDisabled();
    expect(button(version("v1"), "New resource")).toBeDisabled();
    fireEvent.click(button(version("v1"), "New resource"));
    expect(screen.queryByRole("textbox")).toBeNull();

    answer.send(billing({ v1: [INVOICES, { ...PAYMENTS, name: "charges" }, MISC] }));

    expect(await within(version("v1")).findByRole("group", { name: "charges" })).toBeInTheDocument();
    expect(button(version("v1"), "New resource")).toBeEnabled();
    expect(button(resource("v1", "misc"), "Rename resource")).toBeEnabled();
  });
});

describe("adding a resource", () => {
  it("asks for its name as a rename does, and adds it on the server to the version it was asked in", async () => {
    const refunds: LayoutResource = { id: 5, name: "refunds", ...unconfirmed, endpoints: [] };
    const answer = later();
    const { api } = editor({ [ADD]: answer.arrived });
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(version("v1"), "New resource"));
    expect(nameField("Name of the new resource")).toHaveValue("");
    // a second field is not offered while one is open
    expect(within(version("v1")).queryByRole("button", { name: "New resource" })).toBeNull();
    fireEvent.change(nameField("Name of the new resource"), { target: { value: "refunds" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(nameField("Name of the new resource")).toHaveAttribute("readonly"));
    answer.send(billing({ v1: [INVOICES, PAYMENTS, MISC, refunds] }));

    const added = await within(version("v1")).findByRole("group", { name: "refunds" });
    expect(api.sent(ADD)).toEqual([{ api_version: "v1", name: "refunds" }]);
    expect(within(added).getByText("Empty resource — drag endpoints here.")).toBeInTheDocument();
    expect(within(added).getByText("layout not confirmed yet")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText("Changes saved on the service")).toBeInTheDocument();
  });

  it("checks the new name as a rename's: a package name, and free in its version", async () => {
    const { api } = editor({ [ADD]: billing({ v2: [INVOICES_V2, { id: 5, name: "payments", ...unconfirmed, endpoints: [] }] }) });
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(version("v1"), "New resource"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText(/^Package name/)).toBeInTheDocument();
    fireEvent.change(nameField("Name of the new resource"), { target: { value: "payments" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText("A resource with this name already exists in v1.")).toBeInTheDocument();
    fireEvent.keyDown(nameField("Name of the new resource"), { key: "Escape" });
    await settle();
    expect(api.calls(ADD)).toBe(0);

    fireEvent.click(button(version("v2"), "New resource"));
    fireEvent.change(nameField("Name of the new resource"), { target: { value: "payments" } });
    fireEvent.keyDown(nameField("Name of the new resource"), { key: "Enter" });

    expect(await within(version("v2")).findByRole("group", { name: "payments" })).toBeInTheDocument();
    expect(api.sent(ADD)).toEqual([{ api_version: "v2", name: "payments" }]);
  });

  it("opens no other name field while one is open: the name typed is saved or dropped first (ADR-0083)", async () => {
    editor();
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });

    expect(button(version("v2"), "New resource")).toBeDisabled();
    expect(button(resource("v1", "misc"), "Rename resource")).toBeDisabled();
    fireEvent.click(button(version("v2"), "New resource"));
    fireEvent.click(button(resource("v1", "misc"), "Rename resource"));
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(nameField()).toHaveValue("charges");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(button(version("v2"), "New resource")).toBeEnabled();
    expect(button(resource("v1", "misc"), "Rename resource")).toBeEnabled();
  });
});

describe("a refusal of the server", () => {
  it("says why a rename was refused, keeps the name typed, and reads the layout again, shown once the name is dropped (ADR-0083)", async () => {
    const { api, answers } = editor({ [rename(2)]: CONFLICT });
    await screen.findByRole("region", { name: "v1" });
    const reads = api.calls(LAYOUT);
    // someone else took "charges" meanwhile
    answers[LAYOUT] = billing({ v1: [INVOICES, PAYMENTS, { ...MISC, name: "charges" }] });

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("That could not be done right now")).toBeInTheDocument();
    expect(screen.getByText("already there")).toBeInTheDocument();
    expect(nameField()).toHaveValue("charges");
    // the name kept is the user's to change again
    expect(nameField()).not.toHaveAttribute("readonly");
    // the layout read again differs: said so, not shown under the name being typed
    expect(await screen.findByText("Data changed")).toBeInTheDocument();
    expect(api.calls(LAYOUT)).toBe(reads + 1);
    expect(resource("v1", "misc")).toBeInTheDocument();
    expect(screen.queryByText("Changes saved on the service")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    // the query client hands the reset on in its next tick
    await waitFor(() => expect(screen.queryByText("That could not be done right now")).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(resource("v1", "charges")).toBeInTheDocument();
    expect(screen.queryByText("Data changed")).toBeNull();
  });

  it("says why at once, while the layout is still being read again", async () => {
    const reread = later();
    const { answers } = editor({ [rename(2)]: CONFLICT });
    await screen.findByRole("region", { name: "v1" });
    answers[LAYOUT] = () => reread.arrived;

    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("That could not be done right now")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();

    reread.send(billing());
    await settle();
    expect(screen.queryByText("Data changed")).toBeNull();
  });

  it.each([
    [NOT_FOUND, "That did not go through"],
    [FAILED, "That did not go through"],
    [FORBIDDEN, "Your role does not allow that"],
  ])("says so for a move answered %s", async (refusal, title) => {
    const { api } = editor({ [MOVE]: refusal });
    await screen.findByRole("region", { name: "v1" });

    dragTo("List payments", resource("v1", "misc"));

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(api.calls(MOVE)).toBe(1);
    // the layout stays as the server has it
    expect(within(resource("v1", "payments")).getByText("List payments")).toBeInTheDocument();
  });
});

describe("moving an endpoint (ADR-0064)", () => {
  it("moves one into another resource of its version, and shows the layout the server answered with", async () => {
    const moved = billing({ v1: [INVOICES, { ...PAYMENTS, endpoints: [] }, { ...MISC, endpoints: [QUOTAS, LIST_PAYMENTS] }] });
    const { api } = editor({ [MOVE]: moved });
    await screen.findByRole("region", { name: "v1" });

    dragTo("List payments", resource("v1", "misc"));

    await waitFor(() => expect(within(resource("v1", "misc")).getByText("List payments")).toBeInTheDocument());
    expect(api.sent(MOVE)).toEqual([{ path: "payments/list-payments.rst", resource_id: 3 }]);
    expect(within(resource("v1", "payments")).getByText("Empty resource — drag endpoints here.")).toBeInTheDocument();
    expect(screen.getByText("Changes saved on the service")).toBeInTheDocument();
  });

  it("moves one endpoint at a time: nothing is dragged while a move is under way", async () => {
    const answer = later();
    const moved = billing({ v1: [INVOICES, { ...PAYMENTS, endpoints: [] }, { ...MISC, endpoints: [QUOTAS, LIST_PAYMENTS] }] });
    const { api } = editor({ [MOVE]: answer.arrived });
    await screen.findByRole("region", { name: "v1" });

    dragTo("List payments", resource("v1", "misc"));

    await waitFor(() => expect(endpointRow("Check the service")).toHaveAttribute("draggable", "false"));
    expect(endpointRow("Query billing quotas")).toHaveAttribute("draggable", "false");
    expect(endpointRow("List API versions")).toHaveAttribute("draggable", "false");
    dragTo("Check the service", resource("v1", "misc"));
    await settle();
    expect(api.calls(MOVE)).toBe(1);

    answer.send(moved);

    await waitFor(() => expect(within(resource("v1", "misc")).getByText("List payments")).toBeInTheDocument());
    expect(endpointRow("Check the service")).toHaveAttribute("draggable", "true");
  });

  it("moves one out of its version's unassigned list into a resource of that version", async () => {
    const moved = billing({ v1: [INVOICES, PAYMENTS, { ...MISC, endpoints: [QUOTAS, HEALTH] }], unassigned: [] });
    const { api } = editor({ [MOVE]: moved });
    await screen.findByRole("region", { name: "v1" });

    dragTo("Check the service", resource("v1", "misc"));

    await waitFor(() => expect(within(resource("v1", "misc")).getByText("Check the service")).toBeInTheDocument());
    expect(api.sent(MOVE)).toEqual([{ path: "health/check.rst", resource_id: 3 }]);
    expect(within(version("v1")).queryByRole("group", { name: "Unassigned" })).toBeNull();
  });

  it("moves one with no version into a resource of any version", async () => {
    const moved = billing({ v2: [{ ...INVOICES_V2, endpoints: [EXPORT_V2, VERSIONS] }], noVersion: [] });
    const { api } = editor({ [MOVE]: moved });
    await screen.findByRole("region", { name: "v1" });

    dragTo("List API versions", resource("v2", "invoices"));

    await waitFor(() => expect(within(resource("v2", "invoices")).getByText("List API versions")).toBeInTheDocument());
    expect(api.sent(MOVE)).toEqual([{ path: "versions/list-versions.rst", resource_id: 4 }]);
    expect(screen.queryByRole("region", { name: "No version" })).toBeNull();
  });

  it("moves none across versions, from a resource or from the unassigned list", async () => {
    const { api } = editor();
    await screen.findByRole("region", { name: "v1" });

    dragTo("List payments", resource("v2", "invoices"));
    dragTo("Check the service", resource("v2", "invoices"));
    dragTo("Export invoices as CSV", resource("v1", "invoices"));

    await settle();
    expect(api.calls(MOVE)).toBe(0);
    expect(within(resource("v1", "payments")).getByText("List payments")).toBeInTheDocument();
  });

  it("drops nothing into a list: nothing goes back to unassigned or to no version", async () => {
    const { api } = editor();
    await screen.findByRole("region", { name: "v1" });

    dragTo("List payments", within(version("v1")).getByRole("group", { name: "Unassigned" }));
    dragTo("List payments", screen.getByRole("region", { name: "No version" }));
    dragTo("Check the service", screen.getByRole("region", { name: "No version" }));

    await settle();
    expect(api.calls(MOVE)).toBe(0);
  });

  it("sends nothing for an endpoint dropped back into the resource it is in", async () => {
    const { api } = editor();
    await screen.findByRole("region", { name: "v1" });

    dragTo("List payments", resource("v1", "payments"));

    await settle();
    expect(api.calls(MOVE)).toBe(0);
  });

  it("drops the confirmations the server dropped on a move: both resources it touched (ADR-0068)", async () => {
    const moved = billing({
      v1: [{ ...INVOICES, endpoints: [LIST_INVOICES], ...unconfirmed }, { ...PAYMENTS, endpoints: [LIST_PAYMENTS, SHOW_INVOICE] }, MISC],
    });
    editor({ [MOVE]: moved });
    await screen.findByRole("region", { name: "v1" });

    dragTo("Query invoice details", resource("v1", "payments"));

    await waitFor(() => expect(within(resource("v1", "payments")).getByText("Query invoice details")).toBeInTheDocument());
    expect(within(resource("v1", "invoices")).getByText("layout not confirmed yet")).toBeInTheDocument();
    expect(screen.getByText(/· 0 of 4 resources confirmed$/)).toBeInTheDocument();
  });
});

describe("the layout changing under a name being typed (ADR-0083)", () => {
  /** billing-api with "charges" being typed as the new name of payments. */
  async function typing() {
    const opened = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    return opened;
  }

  it("keeps the layout the name was asked on, says the data changed, and shows the layout as it is on Refresh", async () => {
    const { client, answers } = await typing();
    // a rescan took payments away, and someone renamed misc
    answers[LAYOUT] = billing({ v1: [INVOICES, { ...MISC, name: "quotas" }] });
    await refresh(client, keys.genLayout("billing-api"));

    expect(await screen.findByText("Data changed")).toBeInTheDocument();
    expect(nameField()).toHaveValue("charges");
    expect(resource("v1", "misc")).toBeInTheDocument();
    expect(within(version("v1")).queryByRole("group", { name: "quotas" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(screen.queryByRole("textbox")).toBeNull();
    expect(resource("v1", "quotas")).toBeInTheDocument();
    expect(within(version("v1")).queryByRole("group", { name: "payments" })).toBeNull();
    expect(screen.queryByText("Data changed")).toBeNull();
  });

  it("says nothing when a refresh finds the layout as it was", async () => {
    const { client, api } = await typing();
    const reads = api.calls(LAYOUT);

    await refresh(client, keys.genLayout("billing-api"));

    await waitFor(() => expect(api.calls(LAYOUT)).toBe(reads + 1));
    await settle();
    expect(screen.queryByText("Data changed")).toBeNull();
    expect(nameField()).toHaveValue("charges");
  });

  it("says nothing of the user's own save while what the layout feeds is still read again", async () => {
    flags.showGenJobs = true;
    editor({ [rename(2)]: billing({ v1: [INVOICES, { ...PAYMENTS, name: "charges" }, MISC] }) });
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    // the answer is in, and the save stays under way while the resources are read again
    mockFails.holdResources = true;
    const asked = mockFails.resourceCalls;

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(mockFails.resourceCalls).toBe(asked + 1));
    await settle();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.queryByText("Data changed")).toBeNull();
  });

  it("drags nothing while a name is typed: no edit of the user's changes the layout under it", async () => {
    const { api } = await typing();

    for (const title of ["List payments", "Check the service", "List API versions"]) {
      expect(endpointRow(title)).toHaveAttribute("draggable", "false");
    }
    dragTo("Check the service", resource("v1", "misc"));
    await settle();
    expect(api.calls(MOVE)).toBe(0);
    expect(nameField()).toHaveValue("charges");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(endpointRow("Check the service")).toHaveAttribute("draggable", "true");
  });

  it("reads the layout again on Refresh, rather than showing the read the message was about", async () => {
    const { client, api, answers } = await typing();
    answers[LAYOUT] = billing({ v1: [INVOICES, PAYMENTS, { ...MISC, name: "quotas" }] });
    await refresh(client, keys.genLayout("billing-api"));
    expect(await screen.findByText("Data changed")).toBeInTheDocument();
    const reads = api.calls(LAYOUT);
    const lists = api.calls(LIST);
    // changed once more since that read
    answers[LAYOUT] = billing({ v1: [INVOICES, PAYMENTS, { ...MISC, name: "limits" }] });

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await within(version("v1")).findByRole("group", { name: "limits" })).toBeInTheDocument();
    expect(api.calls(LAYOUT)).toBe(reads + 1);
    // the list said nothing new: it is not asked again
    await settle();
    expect(api.calls(LIST)).toBe(lists);
  });

  it("announces the change, and says Refresh loads the page as it is now", async () => {
    const { client, answers } = await typing();
    answers[LAYOUT] = billing({ v1: [INVOICES, PAYMENTS, { ...MISC, name: "quotas" }] });
    await refresh(client, keys.genLayout("billing-api"));

    const notice = (await screen.findByText("Data changed")).closest("[role=status]");
    expect(notice).not.toBeNull();
    expect(notice).toHaveTextContent("Refresh drops the unsaved name and loads the page as it is now.");
  });
});

describe("confirming a resource (ADR-0066, ADR-0067)", () => {
  const confirm = (id: number) => `${LAYOUT}/resources/${id}/confirm`;
  const byAda = { confirmed_by: "ada@otc.test", confirmed_at: "2026-11-20T09:00:00Z" };

  it("confirms the one resource on the server, sending nothing, and shows the answer: the others as they were", async () => {
    const { api } = editor({ [confirm(2)]: billing({ v1: [INVOICES, { ...PAYMENTS, ...byAda }, MISC] }) });
    await screen.findByRole("region", { name: "v1" });

    fireEvent.click(button(resource("v1", "payments"), "Confirm layout"));

    expect(await within(resource("v1", "payments")).findByText(/^confirmed by ada@otc\.test · /)).toBeInTheDocument();
    expect(api.calls(confirm(2))).toBe(1);
    expect(api.sent(confirm(2))).toEqual([]);
    expect(within(resource("v1", "payments")).queryByRole("button", { name: "Confirm layout" })).toBeNull();
    expect(within(resource("v1", "invoices")).getByText(/^confirmed by valeriia · /)).toBeInTheDocument();
    expect(within(resource("v1", "misc")).getByText("layout not confirmed yet")).toBeInTheDocument();
    expect(within(resource("v2", "invoices")).getByText("layout not confirmed yet")).toBeInTheDocument();
    expect(screen.getByText(/· 2 of 4 resources confirmed$/)).toBeInTheDocument();
    // a confirmation is saved on the service as an edit is
    expect(screen.getByText("Changes saved on the service")).toBeInTheDocument();
  });

  it("keeps Confirm unavailable for a resource with an endpoint that is not ok, says why, and blocks no other (ADR-0067)", async () => {
    const { api } = editor();
    await screen.findByRole("region", { name: "v1" });

    const misc = resource("v1", "misc");
    const confirmMisc = button(misc, "Confirm layout");
    expect(confirmMisc).toBeDisabled();
    expect(confirmMisc).toHaveAccessibleDescription("1 endpoint is not ok — move or fix it before confirming.");
    expect(button(resource("v1", "payments"), "Confirm layout")).toBeEnabled();
    expect(button(resource("v2", "invoices"), "Confirm layout")).toBeEnabled();

    fireEvent.click(confirmMisc);
    await settle();
    expect(api.calls(confirm(3))).toBe(0);
  });

  it("counts every endpoint that is not ok", async () => {
    const failed = endpoint({ id: 8, path: "quotas/delete-quota.rst", title: "Delete a quota", overall_status: "failed" });
    editor({ [LAYOUT]: billing({ v1: [INVOICES, PAYMENTS, { ...MISC, endpoints: [QUOTAS, failed, LIST_PAYMENTS] }] }) });
    await screen.findByRole("region", { name: "v1" });

    expect(button(resource("v1", "misc"), "Confirm layout")).toHaveAccessibleDescription(
      "2 endpoints are not ok — move or fix them before confirming.",
    );
  });

  it("keeps Confirm unavailable for a resource without endpoints, and says why", async () => {
    const refunds: LayoutResource = { id: 5, name: "refunds", ...unconfirmed, endpoints: [] };
    editor({ [LAYOUT]: billing({ v1: [INVOICES, PAYMENTS, MISC, refunds] }) });
    await screen.findByRole("region", { name: "v1" });

    const confirmRefunds = button(resource("v1", "refunds"), "Confirm layout");
    expect(confirmRefunds).toBeDisabled();
    expect(confirmRefunds).toHaveAccessibleDescription("No endpoint to confirm yet — drag endpoints here first.");
  });

  it("says why the server refused, in its own words, and reads the layout again", async () => {
    const refusal = "Resource payments has 1 endpoint(s) that are not ok: payments/list-payments.rst";
    const { api } = editor({
      [confirm(2)]: () =>
        new Response(JSON.stringify({ error: { code: "conflict", message: refusal } }), { status: 409 }),
    });
    await screen.findByRole("region", { name: "v1" });
    const reads = api.calls(LAYOUT);

    fireEvent.click(button(resource("v1", "payments"), "Confirm layout"));

    expect(await screen.findByText("That could not be done right now")).toBeInTheDocument();
    expect(screen.getByText(refusal)).toBeInTheDocument();
    await waitFor(() => expect(api.calls(LAYOUT)).toBe(reads + 1));
    expect(within(resource("v1", "payments")).getByText("layout not confirmed yet")).toBeInTheDocument();
    expect(screen.queryByText("Changes saved on the service")).toBeNull();
  });

  it("confirms nothing while another edit is under way or a name is typed: one edit at a time", async () => {
    const answer = later();
    const { api } = editor({ [MOVE]: answer.arrived });
    await screen.findByRole("region", { name: "v1" });

    dragTo("Check the service", resource("v1", "payments"));
    await waitFor(() => expect(button(resource("v1", "payments"), "Confirm layout")).toBeDisabled());
    answer.send(billing({ v1: [INVOICES, { ...PAYMENTS, endpoints: [LIST_PAYMENTS, HEALTH] }, MISC], unassigned: [] }));
    await waitFor(() => expect(button(resource("v1", "payments"), "Confirm layout")).toBeEnabled());

    fireEvent.click(button(version("v2"), "New resource"));
    expect(button(resource("v1", "payments"), "Confirm layout")).toBeDisabled();
    await settle();
    expect(api.calls(confirm(2))).toBe(0);
  });

  it("takes the confirmations from the server's answer to an edit, those it keeps too (ADR-0068)", async () => {
    // the server dropped payments' confirmation on the move, and kept invoices'
    const confirmed = billing({ v1: [INVOICES, { ...PAYMENTS, ...byAda }, MISC] });
    const moved = billing({ v1: [INVOICES, { ...PAYMENTS, endpoints: [LIST_PAYMENTS, HEALTH] }, MISC], unassigned: [] });
    editor({ [LAYOUT]: confirmed, [MOVE]: moved });
    await screen.findByRole("region", { name: "v1" });
    expect(within(resource("v1", "payments")).getByText(/^confirmed by ada@otc\.test · /)).toBeInTheDocument();

    dragTo("Check the service", resource("v1", "payments"));

    await waitFor(() => expect(within(resource("v1", "payments")).getByText("Check the service")).toBeInTheDocument());
    expect(within(resource("v1", "payments")).getByText("layout not confirmed yet")).toBeInTheDocument();
    expect(button(resource("v1", "payments"), "Confirm layout")).toBeEnabled();
    expect(within(resource("v1", "invoices")).getByText(/^confirmed by valeriia · /)).toBeInTheDocument();
  });
});

describe("a viewer (ADR-0070)", () => {
  it("reads the layout with its lists and confirmations, but is offered no way to change it", async () => {
    session.token = tokenWithRoles("viewer");
    const { api } = editor();

    expect(await screen.findByText(/^Shared layout · 2 versions/)).toBeInTheDocument();
    expect(screen.getByText(/· 1 of 4 resources confirmed$/)).toBeInTheDocument();
    expect(within(resource("v1", "invoices")).getByText(/^confirmed by valeriia · /)).toBeInTheDocument();
    expect(within(resource("v1", "payments")).getByText("layout not confirmed yet")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
    expect(within(version("v1")).getByRole("group", { name: "Unassigned" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "No version" })).toBeInTheDocument();
    // why misc cannot be confirmed is a worker's concern: no hint without the control
    expect(screen.queryByText(/before confirming/)).toBeNull();
    for (const name of ["Rename resource", "New resource", "Confirm layout"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    for (const title of ["List payments", "Check the service", "List API versions"]) {
      expect(endpointRow(title)).toHaveAttribute("draggable", "false");
    }

    dragTo("List payments", resource("v1", "misc"));

    await settle();
    expect(api.calls(MOVE)).toBe(0);
  });
});

describe("what the server has no data for yet, switched on", () => {
  it("shows where each resource came from, as the mock has it (SHOW_LAYOUT_ORIGIN)", async () => {
    flags.showLayoutOrigin = true;
    const refunds: LayoutResource = { id: 5, name: "refunds", ...unconfirmed, endpoints: [] };
    editor({ [LAYOUT]: billing({ v1: [INVOICES, PAYMENTS, MISC, refunds] }) });

    await screen.findByRole("region", { name: "v1" });
    expect(within(resource("v1", "payments")).getByText("auto")).toBeInTheDocument();
    expect(within(resource("v1", "misc")).getByText("auto")).toBeInTheDocument();
    expect(within(resource("v2", "invoices")).getByText("new")).toBeInTheDocument();
    // a confirmed resource says that instead, and one the mock does not hold says nothing
    expect(within(resource("v1", "invoices")).getByText("confirmed")).toBeInTheDocument();
    expect(within(resource("v1", "refunds")).queryByText(/^(auto|new)$/)).toBeNull();
    // nothing of the jobs: that is the other flag
    expect(screen.queryByText(/in review/)).toBeNull();
  });

  it("freezes the resource in review on Python SDK, says why, and takes nothing into it (SHOW_GEN_JOBS)", async () => {
    flags.showGenJobs = true;
    const { api } = editor();

    const invoices = await within(await screen.findByRole("region", { name: "v1" })).findByRole("group", { name: "invoices" });
    expect(within(invoices).getByText("in review · Python SDK")).toHaveAttribute(
      "title",
      "Generated for Python SDK and waiting for review — the shared layout is frozen until that pull request is merged or closed.",
    );
    expect(within(invoices).queryByRole("button", { name: "Rename resource" })).toBeNull();
    expect(endpointRow("List invoices of a project")).toHaveAttribute("draggable", "false");
    // v2's invoices is another resource, with no job
    expect(within(resource("v2", "invoices")).queryByText(/in review/)).toBeNull();

    dragTo("List payments", invoices);

    await settle();
    expect(api.calls(MOVE)).toBe(0);
  });

  it("freezes a resource that is generating, says why, and takes nothing into it (SHOW_GEN_JOBS)", async () => {
    flags.showGenJobs = true;
    const running = generationResources("billing-api").map((r) =>
      r.id === "v1_payments" ? { ...r, jobs: { python: { status: "running" as const, pr: null } } } : r,
    );
    const { api } = editor({}, undefined, [[keys.genResources("billing-api"), running]]);

    const payments = await within(await screen.findByRole("region", { name: "v1" })).findByRole("group", { name: "payments" });
    expect(within(payments).getByText("generating · Python SDK")).toHaveAttribute(
      "title",
      "A Python SDK job is running — the shared layout is frozen until it finishes.",
    );
    expect(within(payments).queryByRole("button", { name: "Rename resource" })).toBeNull();
    expect(within(payments).queryByRole("button", { name: "Confirm layout" })).toBeNull();
    expect(endpointRow("List payments")).toHaveAttribute("draggable", "false");

    dragTo("Query billing quotas", payments);

    await settle();
    expect(api.calls(MOVE)).toBe(0);
  });

  it("shows a failed job without freezing the resource (SHOW_GEN_JOBS)", async () => {
    flags.showGenJobs = true;
    const CORE = "/api/generation/services/customer-core/layout";
    const contacts: LayoutResource = { id: 9, name: "contacts", ...unconfirmed, endpoints: [endpoint({ id: 9, title: "List contacts" })] };
    editor(
      { [LIST]: generationList("customer-core"), [CORE]: layout({ versions: [{ api_version: "v1", resources: [contacts], unassigned: [] }] }) },
      "/generation/customer-core/layout",
    );

    const row = await within(await screen.findByRole("region", { name: "v1" })).findByRole("group", { name: "contacts" });
    expect(within(row).getByText("failed · Python SDK")).toBeInTheDocument();
    expect(button(row, "Rename resource")).toBeInTheDocument();
    expect(endpointRow("List contacts")).toHaveAttribute("draggable", "true");
  });

  it("leaves out a resource merged on every connected target, says it moved on, and keeps its name taken (SHOW_GEN_JOBS)", async () => {
    flags.showGenJobs = true;
    const HUB = "/api/generation/services/notifications-hub/layout";
    const topics: LayoutResource = { id: 7, name: "topics", ...unconfirmed, endpoints: [endpoint({ id: 7, path: "t.rst" })] };
    const subscriptions: LayoutResource = { id: 8, name: "subscriptions", ...unconfirmed, endpoints: [endpoint({ id: 8, path: "s.rst" })] };
    const { api } = editor(
      {
        [LIST]: generationList("notifications-hub"),
        [HUB]: layout({ versions: [{ api_version: "v1", resources: [topics, subscriptions], unassigned: [] }] }),
      },
      "/generation/notifications-hub/layout",
    );

    expect(await screen.findByText("1 resource fully merged — moved to Maintenance")).toBeInTheDocument();
    expect(within(version("v1")).getByText("1 resource · 1 endpoint")).toBeInTheDocument();
    // the summary counts what the page shows, as the version does
    expect(screen.getByText(/ · 1 resource · 1 endpoint · 0 of 1 resources confirmed$/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "topics" })).toBeNull();

    fireEvent.click(button(resource("v1", "subscriptions"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "topics" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(screen.getByText("A resource with this name already exists in v1.")).toBeInTheDocument();
    await settle();
    expect(api.calls(`${HUB}/resources/8/rename`)).toBe(0);
  });

  it("keeps the jobs as they were under a name being typed, and says they changed (SHOW_GEN_JOBS, ADR-0083)", async () => {
    flags.showGenJobs = true;
    const { client } = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });

    // a generation of misc starts meanwhile
    const running = generationResources("billing-api").map((r) =>
      r.id === "v1_misc" ? { ...r, jobs: { python: { status: "running" as const, pr: null } } } : r,
    );
    act(() => client.setQueryData(keys.genResources("billing-api"), running));

    expect(await screen.findByText("Data changed")).toBeInTheDocument();
    expect(within(resource("v1", "misc")).queryByText("generating · Python SDK")).toBeNull();
    expect(nameField()).toHaveValue("charges");

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(within(resource("v1", "misc")).getByText("generating · Python SDK")).toBeInTheDocument();
  });

  it("says nothing when the jobs and targets are read again as they were (SHOW_GEN_JOBS, SHOW_LAYOUT_ORIGIN)", async () => {
    flags.showGenJobs = true;
    flags.showLayoutOrigin = true;
    const { client } = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    const asked = mockFails.resourceCalls;

    await pollAgain(client, keys.genTargets, keys.genResources("billing-api"));

    expect(mockFails.resourceCalls).toBe(asked + 1);
    expect(screen.queryByText("Data changed")).toBeNull();
    expect(nameField()).toHaveValue("charges");
  });

  it("keeps the targets as they were under a name being typed, and says they changed (SHOW_GEN_JOBS, ADR-0083)", async () => {
    flags.showGenJobs = true;
    const { client } = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });

    // the Python SDK target is taken away meanwhile
    act(() => client.setQueryData(keys.genTargets, generationTargets().filter((x) => x.id !== "python")));

    expect(await screen.findByText("Data changed")).toBeInTheDocument();
    expect(within(resource("v1", "invoices")).getByText("in review · Python SDK")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(within(resource("v1", "invoices")).queryByText("in review · Python SDK")).toBeNull();
  });

  it("keeps a name being typed through a failed refresh of the jobs, with a warning (SHOW_GEN_JOBS, ADR-0081)", async () => {
    flags.showGenJobs = true;
    const { client } = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });

    mockFails.resources = true;
    await refresh(client, keys.genResources("billing-api"));

    expect(await alertNamed("Could not refresh this layout. Your unsaved name is kept.")).toBeInTheDocument();
    expect(nameField()).toHaveValue("charges");
    expect(screen.queryByText("Failed to load service")).toBeNull();
    expect(screen.queryByText("Data changed")).toBeNull();

    // without a name being typed, the failure takes the page (ADR-0081)
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
  });

  describe("the header, counting what the page shows (SHOW_GEN_JOBS)", () => {
    const HUB = "/api/generation/services/notifications-hub/layout";
    const confirmedBy = { confirmed_by: "valeriia", confirmed_at: "2026-08-11T13:58:00Z" };
    /* The mock has topics merged on every connected target: the page leaves it out. */
    const topics: LayoutResource = { id: 7, name: "topics", ...unconfirmed, endpoints: [endpoint({ id: 7, path: "t.rst" })] };
    const subscriptions: LayoutResource = {
      id: 8,
      name: "subscriptions",
      ...confirmedBy,
      endpoints: [endpoint({ id: 8, path: "s.rst" })],
    };
    const hub = (resources: LayoutResource[]) =>
      editor(
        { [LIST]: generationList("notifications-hub"), [HUB]: layout({ versions: [{ api_version: "v1", resources, unassigned: [] }] }) },
        "/generation/notifications-hub/layout",
      );

    it("says the layout is confirmed when every resource shown is, whatever one moved on was", async () => {
      flags.showGenJobs = true;
      hub([topics, subscriptions]);

      expect(await screen.findByText("1 resource fully merged — moved to Maintenance")).toBeInTheDocument();
      expect(screen.getByText(/ · 1 resource · 1 endpoint · 1 of 1 resources confirmed$/)).toBeInTheDocument();
      expect(screen.getByText("layout confirmed")).toBeInTheDocument();
    });

    it("says the layout is confirmed when every resource has moved on, with no \"0 of 0\"", async () => {
      flags.showGenJobs = true;
      hub([topics]);

      expect(await screen.findByText("1 resource fully merged — moved to Maintenance")).toBeInTheDocument();
      expect(screen.getByText("Shared layout · 1 version · 0 resources · 0 endpoints")).toBeInTheDocument();
      expect(screen.getByText("layout confirmed")).toBeInTheDocument();
    });
  });

  it("shows a failure, not the editor, while the targets fail (SHOW_GEN_JOBS)", async () => {
    flags.showGenJobs = true;
    mockFails.targets = true;
    editor();

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "v1" })).toBeNull();
  });

  it("joins a refresh of the resources already asking when Retry is clicked (ADR-0081, ADR-0084)", async () => {
    flags.showGenJobs = true;
    const { client } = editor();
    expect(await screen.findByRole("region", { name: "v1" })).toBeInTheDocument();
    await expectRetryJoinsResources(client, "billing-api");
  });
});

describe("the way in and out", () => {
  const CORE = "/api/generation/services/customer-core/layout";

  /** The list, the card and the layout under their own routes, so each can be left for the next. */
  function panel(path: string) {
    backend({
      [LIST]: generationList("billing-api", "customer-core"),
      [LAYOUT]: billing(),
      [CORE]: layout(),
      [rename(2)]: billing({ v1: [INVOICES, { ...PAYMENTS, name: "charges" }, MISC] }),
    });
    return renderPage(
      <>
        <Routes>
          <Route path="generation" element={<GenerationListPage />} />
          <Route path="generation/:name" element={<GenerationServicePage />} />
          <Route path="generation/:name/layout" element={<GenerationLayoutPage />} />
        </Routes>
        <Location />
      </>,
      { path, route: "*" },
    );
  }
  const location = () => screen.getByTestId("location").textContent;

  it("goes from the list to the card, on to the layout and back", async () => {
    panel("/generation");

    fireEvent.click(await screen.findByText("billing-api"));
    fireEvent.click(await screen.findByRole("link", { name: "Edit layout" }));

    expect(location()).toBe("/generation/billing-api/layout");
    expect(await screen.findByText(/^Shared layout · 2 versions/)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);

    expect(location()).toBe("/generation/billing-api");
    expect(await screen.findByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
  });

  it("keeps the note that changes were saved once the layout is left, for that service only", async () => {
    panel("/generation/billing-api/layout");

    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Changes saved on the service")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);
    fireEvent.click(await screen.findByRole("link", { name: "Edit layout" }));

    expect(await screen.findByRole("group", { name: "charges" })).toBeInTheDocument();
    expect(screen.getByText("Changes saved on the service")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);
    fireEvent.click(await screen.findByRole("link", { name: "All services" }));
    fireEvent.click(await screen.findByText("customer-core"));
    fireEvent.click((await screen.findAllByRole("link", { name: "Edit layout" }))[0]);

    expect(await screen.findByRole("group", { name: "cloudservers" })).toBeInTheDocument();
    expect(location()).toBe("/generation/customer-core/layout");
    expect(screen.queryByText("Changes saved on the service")).toBeNull();
  });

  it("drops a name being typed when the page is reused for another service: its layout is not the other's", async () => {
    const contacts: LayoutResource = { id: 9, name: "contacts", ...unconfirmed, endpoints: [endpoint({ id: 9, title: "List contacts" })] };
    backend({
      [LIST]: generationList("billing-api", "customer-core"),
      [LAYOUT]: billing(),
      [CORE]: layout({ versions: [{ api_version: "v1", resources: [contacts], unassigned: [] }] }),
    });
    renderPage(
      <>
        <GenerationLayoutPage />
        <Link to="/generation/customer-core/layout">customer-core</Link>
      </>,
      { path: "/generation/billing-api/layout", route: "/generation/:name/layout" },
    );
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });

    fireEvent.click(screen.getByRole("link", { name: "customer-core" }));

    expect(await screen.findByRole("group", { name: "contacts" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "payments" })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("changes nothing on a layout opened again while an edit sent before is under way: its answer is not shown over a newer one", async () => {
    const answer = later();
    backend({ [LIST]: generationList("billing-api"), [LAYOUT]: billing(), [rename(2)]: answer.arrived });
    renderPage(
      <Routes>
        <Route path="generation/:name" element={<GenerationServicePage />} />
        <Route path="generation/:name/layout" element={<GenerationLayoutPage />} />
      </Routes>,
      { path: "/generation/billing-api/layout", route: "*" },
    );
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeDisabled());

    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);
    fireEvent.click(await screen.findByRole("link", { name: "Edit layout" }));

    await screen.findByRole("region", { name: "v1" });
    // no name is open on this page: what holds it is the edit the last one sent
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(button(version("v1"), "New resource")).toBeDisabled();
    expect(button(resource("v1", "misc"), "Rename resource")).toBeDisabled();
    expect(button(resource("v1", "payments"), "Confirm layout")).toBeDisabled();
    expect(endpointRow("Check the service")).toHaveAttribute("draggable", "false");

    answer.send(billing({ v1: [INVOICES, { ...PAYMENTS, name: "charges" }, MISC] }));

    expect(await within(version("v1")).findByRole("group", { name: "charges" })).toBeInTheDocument();
    expect(button(version("v1"), "New resource")).toBeEnabled();
    expect(button(resource("v1", "misc"), "Rename resource")).toBeEnabled();
    expect(button(resource("v1", "charges"), "Confirm layout")).toBeEnabled();
    expect(endpointRow("Check the service")).toHaveAttribute("draggable", "true");
  });

  it("keeps the card's target on the way back", async () => {
    editor({}, "/generation/billing-api/layout?target=ansible");

    await screen.findByRole("region", { name: "v1" });
    for (const link of await screen.findAllByRole("link", { name: "Back to generation" })) {
      expect(link).toHaveAttribute("href", "/generation/billing-api?target=ansible");
    }
  });

  it.each(["cobol", "python"])("leaves ?target=%s off the way back, as the card's own link does", async (target) => {
    editor({}, `/generation/billing-api/layout?target=${target}`);

    await screen.findByRole("region", { name: "v1" });
    for (const link of await screen.findAllByRole("link", { name: "Back to generation" })) {
      await waitFor(() => expect(link).toHaveAttribute("href", "/generation/billing-api"));
    }
  });

  it("opens the editor without targets: the layout is the same for every one (ADR-0074)", async () => {
    mockFails.noTargets = true;
    editor();

    expect(await screen.findByRole("region", { name: "v1" })).toBeInTheDocument();
    expect(screen.queryByText("No target to generate for")).toBeNull();
  });

  it("opens the editor while the targets fail, taking the address's target along as it is", async () => {
    mockFails.targets = true;
    editor({}, "/generation/billing-api/layout?target=python");

    expect(await screen.findByRole("region", { name: "v1" })).toBeInTheDocument();
    expect(screen.queryByText("Failed to load service")).toBeNull();
    expect(screen.getAllByRole("link", { name: "Back to generation" })[0]).toHaveAttribute(
      "href",
      "/generation/billing-api?target=python",
    );
  });
});

describe("no layout to edit", () => {
  const ecs = "opentelekomcloud-docs/ecs";
  const ECS_LAYOUT = "/api/generation/services/opentelekomcloud-docs%2Fecs/layout";
  const NO_LAYOUT = layout({ has_layout: false, versions: [], no_version: [] });

  it("says there is no layout yet before the grouping has run, and leads to the service page (ADR-0086)", async () => {
    editor({ [LIST]: generationList(ecs), [ECS_LAYOUT]: NO_LAYOUT }, "/generation/opentelekomcloud-docs%2Fecs/layout");

    expect(await screen.findByRole("heading", { name: ecs })).toBeInTheDocument();
    expect(screen.getByText("No layout yet. Its resources appear here once the service is grouped.")).toBeInTheDocument();
    expect(screen.getByText("no layout yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the service page" })).toHaveAttribute(
      "href",
      "/generation/opentelekomcloud-docs%2Fecs",
    );
    expect(screen.getByRole("link", { name: "Back to generation" })).toHaveAttribute(
      "href",
      "/generation/opentelekomcloud-docs%2Fecs",
    );
    // an empty state in place, not a redirect, and no editor
    expect(screen.getByTestId("location")).toHaveTextContent("/generation/opentelekomcloud-docs%2Fecs/layout");
    expect(screen.queryByRole("region")).toBeNull();
    expect(screen.queryByText(/^Shared layout/)).toBeNull();
  });

  it("carries the target the address names on the way to the service page", async () => {
    editor({ [LIST]: generationList(ecs), [ECS_LAYOUT]: NO_LAYOUT }, "/generation/opentelekomcloud-docs%2Fecs/layout?target=ansible");

    expect(await screen.findByRole("link", { name: "Open the service page" })).toHaveAttribute(
      "href",
      "/generation/opentelekomcloud-docs%2Fecs?target=ansible",
    );
  });

  it("reads the targets as they stand, not their answer before a failed refresh (ADR-0081)", async () => {
    // the default named in the address: the current targets leave it off, as the card does
    const { client } = editor(
      { [LIST]: generationList(ecs), [ECS_LAYOUT]: NO_LAYOUT },
      "/generation/opentelekomcloud-docs%2Fecs/layout?target=python",
    );
    const serviceLink = () => screen.getByRole("link", { name: "Open the service page" });
    await waitFor(() => expect(serviceLink()).toHaveAttribute("href", "/generation/opentelekomcloud-docs%2Fecs"));

    // TanStack keeps the last targets through a failed refresh; not read as current, they
    // decide nothing, and the address's target rides along as it is
    mockFails.targets = true;
    await refresh(client, keys.genTargets);

    await waitFor(() =>
      expect(serviceLink()).toHaveAttribute("href", "/generation/opentelekomcloud-docs%2Fecs?target=python"),
    );
  });
});

describe("the services the layout opens for (ADR-0086)", () => {
  it("does not open a service that the server's list does not hold", async () => {
    editor({ [LIST]: generationList("customer-core") });

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "billing-api" })).toBeNull();
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
  });

  it("turns into the page a direct address shows once a refresh no longer lists the service", async () => {
    const { client, answers } = editor();
    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();

    answers[LIST] = [];
    await refresh(client, keys.genList());

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
  });

  it("shows a failed refresh of the list as a failure with Retry, not as Page not found", async () => {
    const { client, answers } = editor();
    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();

    answers[LIST] = FAILED;
    await refresh(client, keys.genList());

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByText("Page not found.")).toBeNull();

    answers[LIST] = generationList("billing-api");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();
  });

  it("keeps a name being typed through a failed refresh of the list, with a warning and Retry", async () => {
    const { client, answers } = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });

    answers[LIST] = FAILED;
    await refresh(client, keys.genList());

    const warning = await alertNamed("Could not refresh this layout. Your unsaved name is kept.");
    expect(nameField()).toHaveValue("charges");
    expect(screen.queryByText("Failed to load service")).toBeNull();
    expect(screen.queryByText("Page not found.")).toBeNull();

    answers[LIST] = generationList("billing-api");
    fireEvent.click(within(warning).getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(nameField()).toHaveValue("charges");
  });

  it("asks for the layout next to the list, not after it", async () => {
    const list = later();
    const { api } = editor({ [LIST]: list.arrived });

    await waitFor(() => expect(api.calls(LAYOUT)).toBe(1));
    expect(api.calls(LIST)).toBe(1);

    list.send(generationList("billing-api"));
    expect(await screen.findByRole("region", { name: "v1" })).toBeInTheDocument();
  });

  it("turns into the page a direct address shows when the layout answers 404, though the list still holds it", async () => {
    const { client, answers } = editor();
    expect(await screen.findByRole("region", { name: "v1" })).toBeInTheDocument();

    // excluded between the list's answer and the layout's (ADR-0086)
    answers[LAYOUT] = NOT_FOUND;
    await refresh(client, keys.genLayout("billing-api"));

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.queryByText("Failed to load service")).toBeNull();
  });

  it("keeps a name being typed when the layout answers 404 as the list fails, and shows Page not found on Refresh (ADR-0082)", async () => {
    const { client, api, answers } = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });

    // one round of the periodic refresh: the list fails, and the layout says the service is gone
    answers[LIST] = FAILED;
    answers[LAYOUT] = NOT_FOUND;
    await pollAgain(client, keys.genList(), keys.genLayout("billing-api"));

    expect(await screen.findByText("Data changed")).toBeInTheDocument();
    expect(nameField()).toHaveValue("charges");
    expect(screen.queryByText("Page not found.")).toBeNull();
    expect(screen.queryByText("Could not refresh this layout. Your unsaved name is kept.")).toBeNull();
    const reads = api.calls(LAYOUT);

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    // a service that has left is not asked for again
    await settle();
    expect(api.calls(LAYOUT)).toBe(reads);
  });

  it("keeps a name being typed when a refresh no longer lists the service, and shows Page not found on Refresh (ADR-0082)", async () => {
    const { client, api, answers } = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(version("v1"), "New resource"));
    fireEvent.change(nameField("Name of the new resource"), { target: { value: "refunds" } });

    answers[LIST] = generationList("customer-core");
    await refresh(client, keys.genList());

    expect(await screen.findByText("Data changed")).toBeInTheDocument();
    expect(nameField("Name of the new resource")).toHaveValue("refunds");
    expect(resource("v1", "payments")).toBeInTheDocument();
    // a service that has left takes no edit: nothing is sent to be refused
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.keyDown(nameField("Name of the new resource"), { key: "Enter" });
    await settle();
    expect(api.calls(ADD)).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
  });

  it("stops asking for the layout of a repo off the list, which the backend answers 404", async () => {
    const { client, api } = editor({ [LIST]: generationList("customer-core"), [LAYOUT]: NOT_FOUND });
    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    const asked = api.calls(LAYOUT);

    await pollAgain(client, keys.genLayout("billing-api"));

    expect(api.calls(LAYOUT)).toBe(asked);
    expect(screen.getByText("Page not found.")).toBeInTheDocument();
  });

  it("shows a layout that failed to load as a failure with Retry, not as Page not found or as no layout", async () => {
    const { answers } = editor({ [LAYOUT]: FAILED });

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByText("Page not found.")).toBeNull();
    expect(screen.queryByText("No layout yet. Its resources appear here once the service is grouped.")).toBeNull();

    answers[LAYOUT] = billing();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("region", { name: "v1" })).toBeInTheDocument();
  });

  it("shows a failed refresh of the layout as a failure, and keeps the layout and a name being typed through it", async () => {
    const { client, answers } = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(nameField(), { target: { value: "charges" } });

    answers[LAYOUT] = FAILED;
    await refresh(client, keys.genLayout("billing-api"));

    const warning = await alertNamed("Could not refresh this layout. Your unsaved name is kept.");
    expect(nameField()).toHaveValue("charges");
    expect(screen.queryByText("Failed to load service")).toBeNull();
    // the layout last read stays under the name being typed
    expect(within(resource("v1", "invoices")).getByText("List invoices of a project")).toBeInTheDocument();

    answers[LAYOUT] = billing();
    fireEvent.click(within(warning).getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(nameField()).toHaveValue("charges");

    // without a name being typed, a failed refresh replaces the layout (ADR-0081)
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    answers[LAYOUT] = FAILED;
    await refresh(client, keys.genLayout("billing-api"));

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "v1" })).toBeNull();
  });

  it("keeps the name of a resource being added through a failed refresh of the layout", async () => {
    const { client, answers } = editor();
    await screen.findByRole("region", { name: "v1" });
    fireEvent.click(button(version("v1"), "New resource"));
    fireEvent.change(nameField("Name of the new resource"), { target: { value: "refunds" } });

    answers[LAYOUT] = FAILED;
    await refresh(client, keys.genLayout("billing-api"));

    expect(await alertNamed("Could not refresh this layout. Your unsaved name is kept.")).toBeInTheDocument();
    expect(nameField("Name of the new resource")).toHaveValue("refunds");
  });
});
