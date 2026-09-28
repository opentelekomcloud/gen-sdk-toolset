import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router";
import { renderPage } from "../../../test/render";
import { tokenWithRoles } from "../../../test/token";
import { keys } from "../../scan/api/queries";
import { generationResources, resetGenerationMock } from "../data/mock";
import { GenerationLayoutPage } from "./GenerationLayoutPage";
import { GenerationListPage } from "./GenerationListPage";
import { GenerationServicePage } from "./GenerationServicePage";

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

/* The mock lives in module memory, and the edits below change it. */
beforeEach(() => {
  resetGenerationMock();
  session.token = tokenWithRoles("worker");
});

/** Where the page navigated to. */
function Location() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}

function layoutPage(path = "/generation/billing-api/layout", seed?: [readonly unknown[], unknown][]) {
  return renderPage(
    <>
      <GenerationLayoutPage />
      <Location />
    </>,
    { path, route: "/generation/:name/layout", seed },
  );
}

const version = (id: string) => screen.getByRole("region", { name: id });
const resource = (versionId: string, name: string) => within(version(versionId)).getByRole("group", { name });
/** An endpoint's row, by its document's title: a GET and a POST can share one URI. */
const endpointRow = (title: string) => screen.getByText(title).closest("[draggable]") as HTMLElement;
const button = (scope: HTMLElement, name: string | RegExp) => within(scope).getByRole("button", { name });

/** Drag an endpoint onto a resource, as the browser fires it. */
function dragTo(title: string, target: HTMLElement) {
  fireEvent.dragStart(endpointRow(title));
  fireEvent.dragOver(target);
  fireEvent.drop(target);
}

describe("the billing-api layout on the in-memory mock", () => {
  it("shows every version with its resources and endpoints, the summary and the way back", async () => {
    layoutPage();

    expect(screen.getByText("Loading service…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();
    expect(screen.getByText("needs confirmation")).toBeInTheDocument();
    expect(
      screen.getByText("Shared layout · 2 versions · 4 resources · 12 endpoints · 1 of 4 resources confirmed"),
    ).toBeInTheDocument();
    expect(screen.getByText(/This layout is shared by every target/)).toBeInTheDocument();
    expect(within(version("v1")).getByText("3 resources · 10 endpoints")).toBeInTheDocument();
    expect(within(version("v2")).getByText("1 resource · 2 endpoints")).toBeInTheDocument();

    const invoices = resource("v1", "invoices");
    expect(within(invoices).getByText("4 endpoints")).toBeInTheDocument();
    expect(within(invoices).getByText("confirmed")).toBeInTheDocument();
    expect(within(invoices).getByText(/^confirmed by valeriia · \d\d\/\d\d\/2026, \d\d:\d\d$/)).toBeInTheDocument();
    expect(within(resource("v1", "payments")).getByText("auto")).toBeInTheDocument();
    expect(within(resource("v1", "misc")).getByText("auto")).toBeInTheDocument();
    expect(within(resource("v2", "invoices")).getByText("new")).toBeInTheDocument();

    const quotas = endpointRow("Query billing quotas");
    expect(within(quotas).getByText("GET")).toBeInTheDocument();
    expect(within(quotas).getByText("/v1/billing/quotas")).toBeInTheDocument();
    expect(within(quotas).getByTitle("Open this document in the repository at the scanned commit")).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/billing-api/blob/mockcommit/api-ref/source/quotas/show-quotas.rst",
    );

    const back = screen.getAllByRole("link", { name: "Back to generation" });
    expect(back).toHaveLength(2);
    for (const link of back) expect(link).toHaveAttribute("href", "/generation/billing-api");
    expect(screen.queryByText("Layout edited · saved on the service")).toBeNull();
  });

  it("freezes the resource in review on Python SDK, and says why", async () => {
    layoutPage();

    const invoices = (await screen.findAllByRole("group", { name: "invoices" }))[0];
    expect(within(invoices).getByText("in review · Python SDK")).toHaveAttribute(
      "title",
      "Generated for Python SDK and waiting for review — the shared layout is frozen until that pull request is merged or closed.",
    );
    expect(within(invoices).queryByRole("button", { name: "Confirm layout" })).toBeNull();
    expect(within(invoices).queryByRole("button", { name: "Rename resource" })).toBeNull();
    expect(within(invoices).queryByRole("button", { name: "Reset to auto" })).toBeNull();
    expect(endpointRow("Query invoice details")).toHaveAttribute("draggable", "false");

    // the other resources stay editable
    const payments = resource("v1", "payments");
    expect(button(payments, "Confirm layout")).toBeInTheDocument();
    expect(button(payments, "Rename resource")).toBeInTheDocument();
    expect(button(payments, "Reset to auto")).toBeInTheDocument();
    expect(endpointRow("List payments")).toHaveAttribute("draggable", "true");

    // and nothing lands in the frozen one
    dragTo("List payments", invoices);

    expect(within(invoices).getByText("4 endpoints")).toBeInTheDocument();
    expect(within(resource("v1", "payments")).getByText("List payments")).toBeInTheDocument();
    expect(generationResources("billing-api").find((r) => r.id === "v1_payments")?.endpoints).toHaveLength(3);
  });

  it("marks the endpoint whose document is not recognized in full, and lets it be moved", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    const quotas = endpointRow("Query billing quotas");
    expect(within(quotas).getByText("partial")).toHaveAttribute(
      "title",
      "Not recognized in full — a resource holding this endpoint cannot be generated. It can be dragged to another resource.",
    );
    expect(quotas).toHaveAttribute("draggable", "true");
    expect(within(endpointRow("List credit notes")).queryByText("partial")).toBeNull();
    expect(screen.getAllByText("partial")).toHaveLength(1);
  });

  it("moves an endpoint by dragging it onto another resource, across versions too", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    dragTo("Query billing quotas", resource("v1", "payments"));

    expect(await within(resource("v1", "payments")).findByText("Query billing quotas")).toBeInTheDocument();
    expect(within(resource("v1", "payments")).getByText("4 endpoints")).toBeInTheDocument();
    expect(within(resource("v1", "misc")).getByText("2 endpoints")).toBeInTheDocument();
    // moving does not confirm
    expect(within(resource("v1", "payments")).getByText("auto")).toBeInTheDocument();
    expect(screen.getByText("Layout edited · saved on the service")).toBeInTheDocument();

    dragTo("Export invoices as CSV", resource("v1", "misc"));

    expect(await within(resource("v1", "misc")).findByText("Export invoices as CSV")).toBeInTheDocument();
    expect(within(version("v2")).getByText("1 resource · 1 endpoint")).toBeInTheDocument();
  });

  it("renames a resource once the name passes, without confirming it", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    const input = screen.getByRole("textbox", { name: "Rename resource" });
    expect(input).toHaveValue("payments");

    fireEvent.change(input, { target: { value: "Bad Name" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(
      screen.getByText("Package name: lowercase latin, digits and underscores, starting with a letter."),
    ).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "misc" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByText("A resource with this name already exists in v1.")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: " charges " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const charges = await within(version("v1")).findByRole("group", { name: "charges" });
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(within(charges).getByText("auto")).toBeInTheDocument();
    expect(button(charges, "Confirm layout")).toBeInTheDocument();
    expect(screen.getByText(/· 1 of 4 resources confirmed$/)).toBeInTheDocument();
  });

  it("takes a name another version already has, and drops a rename on Escape or Cancel", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    fireEvent.click(button(resource("v2", "invoices"), "Rename resource"));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "payments" } });
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });

    expect(await within(version("v2")).findByRole("group", { name: "payments" })).toBeInTheDocument();

    fireEvent.click(button(resource("v1", "misc"), "Rename resource"));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "notes" } });
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Escape" });
    expect(screen.queryByRole("textbox")).toBeNull();

    fireEvent.click(button(resource("v1", "misc"), "Rename resource"));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(resource("v1", "misc")).toBeInTheDocument();
  });

  it("confirms a resource with the button, recording who and when", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    fireEvent.click(button(resource("v1", "payments"), "Confirm layout"));

    const payments = resource("v1", "payments");
    expect(await within(payments).findByText("confirmed")).toBeInTheDocument();
    expect(within(payments).getByText(/^confirmed by ada@otc\.test · \d\d\/\d\d\/\d{4}, \d\d:\d\d$/)).toBeInTheDocument();
    expect(within(payments).queryByRole("button", { name: "Confirm layout" })).toBeNull();
    expect(screen.getByText(/· 2 of 4 resources confirmed$/)).toBeInTheDocument();

    const recorded = generationResources("billing-api").find((r) => r.id === "v1_payments");
    expect(recorded?.confirmedBy).toBe("ada@otc.test");
    expect(Date.now() - Date.parse(recorded?.confirmedAt ?? "")).toBeLessThan(60_000);
  });

  it("makes an empty resource at the end of its version, which nobody has confirmed", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    fireEvent.click(button(version("v1"), "New resource"));

    const made = await within(version("v1")).findByRole("group", { name: "new_resource_1" });
    expect(within(made).getByText("0 endpoints")).toBeInTheDocument();
    expect(within(made).getByText("new")).toBeInTheDocument();
    expect(within(made).getByText("Empty resource — drag endpoints here.")).toBeInTheDocument();
    expect(button(made, "Confirm layout")).toBeInTheDocument();
    expect(within(version("v1")).getByText("4 resources · 10 endpoints")).toBeInTheDocument();
    expect(screen.getByText(/· 5 resources · 12 endpoints · 1 of 5 resources confirmed$/)).toBeInTheDocument();
    expect(within(version("v1")).getAllByRole("group").at(-1)).toBe(made);

    fireEvent.click(button(version("v1"), "New resource"));

    expect(await within(version("v1")).findByRole("group", { name: "new_resource_2" })).toBeInTheDocument();
  });

  it("resets a resource to the scanner's layout, and an endpoint moved into it goes home", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    dragTo("Query billing quotas", resource("v1", "payments"));
    await within(resource("v1", "payments")).findByText("Query billing quotas");
    fireEvent.click(button(resource("v1", "payments"), "Rename resource"));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "charges" } });
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    const charges = await within(version("v1")).findByRole("group", { name: "charges" });

    fireEvent.click(button(charges, "Reset to auto"));

    const payments = await within(version("v1")).findByRole("group", { name: "payments" });
    expect(within(payments).getByText("3 endpoints")).toBeInTheDocument();
    expect(within(resource("v1", "misc")).getByText("Query billing quotas")).toBeInTheDocument();
    expect(within(resource("v1", "misc")).getByText("3 endpoints")).toBeInTheDocument();
  });

  it("leaves a resource made by hand as it is on its reset: the scanner's layout has no such resource", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    fireEvent.click(button(version("v1"), "New resource"));
    const made = await within(version("v1")).findByRole("group", { name: "new_resource_1" });
    dragTo("List credit notes", made);
    await within(resource("v1", "new_resource_1")).findByText("List credit notes");

    fireEvent.click(button(resource("v1", "new_resource_1"), "Reset to auto"));
    // edits go through in the order they are made: once the confirmation shows, the reset has been through
    fireEvent.click(button(resource("v1", "new_resource_1"), "Confirm layout"));

    expect(await within(resource("v1", "new_resource_1")).findByText("confirmed")).toBeInTheDocument();
    expect(within(resource("v1", "new_resource_1")).getByText("List credit notes")).toBeInTheDocument();
    expect(within(resource("v1", "misc")).getByText("2 endpoints")).toBeInTheDocument();
    expect(screen.queryByText("That did not go through")).toBeNull();
  });

  it("resets a version: names, endpoints and confirmations come back, resources made by hand go", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    fireEvent.click(button(resource("v1", "payments"), "Confirm layout"));
    await within(resource("v1", "payments")).findByText("confirmed");
    fireEvent.click(button(resource("v1", "misc"), "Rename resource"));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "notes" } });
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    await within(version("v1")).findByRole("group", { name: "notes" });
    fireEvent.click(button(version("v1"), "New resource"));
    const made = await within(version("v1")).findByRole("group", { name: "new_resource_1" });
    dragTo("List payments", made);
    await within(resource("v1", "new_resource_1")).findByText("List payments");
    dragTo("List invoices (v2)", resource("v1", "notes"));
    await within(resource("v1", "notes")).findByText("List invoices (v2)");

    // the version's own button, ahead of its resources' ones
    fireEvent.click(within(version("v1")).getAllByRole("button", { name: "Reset to auto" })[0]);

    expect(await within(version("v1")).findByRole("group", { name: "misc" })).toBeInTheDocument();
    expect(within(version("v1")).queryByRole("group", { name: "new_resource_1" })).toBeNull();
    expect(within(version("v1")).queryByRole("group", { name: "notes" })).toBeNull();
    const payments = resource("v1", "payments");
    expect(within(payments).getByText("auto")).toBeInTheDocument();
    expect(button(payments, "Confirm layout")).toBeInTheDocument();
    expect(within(payments).getByText("List payments")).toBeInTheDocument();
    // the endpoint from v2 is back in v2, and the frozen resource did not move
    expect(within(resource("v2", "invoices")).getByText("List invoices (v2)")).toBeInTheDocument();
    expect(within(resource("v1", "invoices")).getByText("in review · Python SDK")).toBeInTheDocument();
    expect(
      screen.getByText("Shared layout · 2 versions · 4 resources · 12 endpoints · 1 of 4 resources confirmed"),
    ).toBeInTheDocument();
  });

  it("folds a version and a resource", async () => {
    layoutPage();

    await screen.findByRole("heading", { name: "billing-api" });
    fireEvent.click(button(resource("v1", "payments"), "payments"));

    expect(screen.queryByText("Update payment method")).toBeNull();
    expect(button(resource("v1", "payments"), "payments")).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Query billing quotas")).toBeInTheDocument();

    fireEvent.click(button(version("v1"), "v1"));

    expect(within(version("v1")).queryByRole("group")).toBeNull();
    expect(within(version("v1")).getByText("3 resources · 10 endpoints")).toBeInTheDocument();
    expect(resource("v2", "invoices")).toBeInTheDocument();

    fireEvent.click(button(version("v1"), "v1"));

    expect(resource("v1", "misc")).toBeInTheDocument();
  });
});

describe("a viewer", () => {
  it("reads the layout, but is offered no way to change it", async () => {
    session.token = tokenWithRoles("viewer");
    layoutPage();

    expect(await screen.findByText(/^Shared layout · 2 versions/)).toBeInTheDocument();
    expect(resource("v1", "payments")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
    for (const name of ["Confirm layout", "Rename resource", "Reset to auto", "New resource"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(endpointRow("List payments")).toHaveAttribute("draggable", "false");

    dragTo("List payments", resource("v1", "misc"));

    expect(within(resource("v1", "misc")).queryByText("List payments")).toBeNull();
  });
});

describe("the way in and out", () => {
  /** The list, the card and the layout under their own routes, so each can be left for the next. */
  function panel(path: string) {
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

  it("goes from the card to the layout and back, and the card still leads back to the list it came from", async () => {
    panel("/generation?filter=review");

    fireEvent.click(await screen.findByText("billing-api"));
    fireEvent.click(await screen.findByRole("link", { name: "Edit layout" }));

    expect(location()).toBe("/generation/billing-api/layout");
    expect(await screen.findByText(/^Shared layout · 2 versions/)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);

    expect(location()).toBe("/generation/billing-api");
    expect(await screen.findByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation?filter=review");
  });

  it("keeps the note that the layout was edited once the layout is left, for that service only", async () => {
    panel("/generation/billing-api/layout");

    await screen.findByText(/^Shared layout · 2 versions/);
    fireEvent.click(button(version("v1"), "New resource"));
    expect(await screen.findByText("Layout edited · saved on the service")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);
    fireEvent.click(await screen.findByRole("link", { name: "Edit layout" }));

    expect(await screen.findByText(/^Shared layout · 2 versions · 5 resources/)).toBeInTheDocument();
    expect(screen.getByText("Layout edited · saved on the service")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);
    fireEvent.click(await screen.findByRole("link", { name: "All services" }));
    fireEvent.click(await screen.findByText("customer-core"));
    fireEvent.click(await screen.findByRole("link", { name: "Edit layout" }));

    expect(await screen.findByText(/^Shared layout · 1 version/)).toBeInTheDocument();
    expect(location()).toBe("/generation/customer-core/layout");
    expect(screen.queryByText("Layout edited · saved on the service")).toBeNull();
  });

  it("keeps the card's target on the way back", async () => {
    layoutPage("/generation/billing-api/layout?target=ansible");

    for (const link of await screen.findAllByRole("link", { name: "Back to generation" })) {
      expect(link).toHaveAttribute("href", "/generation/billing-api?target=ansible");
    }
  });
});

describe("other services on the mock", () => {
  it("leaves out a resource merged on every connected target, and says it moved on", async () => {
    layoutPage("/generation/notifications-hub/layout");

    expect(
      await screen.findByText("Shared layout · 1 version · 2 resources · 5 endpoints · 1 of 2 resources confirmed"),
    ).toBeInTheDocument();
    expect(within(version("v1")).getByText("1 resource · 2 endpoints")).toBeInTheDocument();
    expect(within(version("v1")).getByText("1 resource fully merged — moved to Maintenance")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "topics" })).toBeNull();
    expect(resource("v1", "subscriptions")).toBeInTheDocument();
  });

  it("shows a failed job without freezing the resource", async () => {
    layoutPage("/generation/customer-core/layout");

    const contacts = await within(await screen.findByRole("region", { name: "v1" })).findByRole("group", {
      name: "contacts",
    });
    expect(within(contacts).getByText("failed · Python SDK")).toHaveAttribute(
      "title",
      "The last Python SDK job failed and wrote nothing — the layout stays editable, retry from the error screen.",
    );
    expect(button(contacts, "Confirm layout")).toBeInTheDocument();
    expect(within(resource("v1", "addresses")).getByText("new")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "customers" })).toBeNull();
  });

  it("lays out device-mgmt, scanned in part, from its documents, and marks the ones not recognized in full", async () => {
    layoutPage("/generation/device-mgmt/layout");

    expect(
      await screen.findByText("Shared layout · 1 version · 6 resources · 31 endpoints · 0 of 6 resources confirmed"),
    ).toBeInTheDocument();
    expect(screen.getByText("needs confirmation")).toBeInTheDocument();
    expect(within(version("v2")).getAllByText("auto")).toHaveLength(6);
    // the scan mock has 18 of its documents ok, 9 partial and 4 failed
    expect(screen.getAllByText("partial")).toHaveLength(9);
    expect(screen.getAllByText("failed")).toHaveLength(4);
    const shadow = endpointRow("Query a device shadow");
    expect(within(shadow).getByText("failed")).toHaveAttribute(
      "title",
      "Not recognized in full — a resource holding this endpoint cannot be generated. It can be dragged to another resource.",
    );
    expect(shadow).toHaveAttribute("draggable", "true");
    expect(screen.queryByText("Scanned — no endpoint documents found. Nothing to lay out.")).toBeNull();
    expect(screen.queryByText("nothing to lay out")).toBeNull();
  });

  it("says there is nothing to lay out", async () => {
    layoutPage("/generation/tariff-catalog/layout");

    expect(await screen.findByText("Scanned — no endpoint documents found. Nothing to lay out.")).toBeInTheDocument();
    expect(screen.getByText("nothing to lay out")).toBeInTheDocument();
    expect(screen.getByText("Shared layout · 0 versions · 0 resources · 0 endpoints")).toBeInTheDocument();
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("does not open a service that is not in Generation", async () => {
    layoutPage("/generation/sms-gateway/layout");

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
  });
});

describe("states the mock does not hold today", () => {
  it("freezes a resource that is generating", async () => {
    const running = generationResources("billing-api").map((r) =>
      r.id === "v1_payments" ? { ...r, jobs: { python: { status: "running" as const, pr: null } } } : r,
    );
    layoutPage("/generation/billing-api/layout", [[keys.genResources("billing-api"), running]]);

    const payments = await within(await screen.findByRole("region", { name: "v1" })).findByRole("group", {
      name: "payments",
    });
    expect(within(payments).getByText("generating · Python SDK")).toHaveAttribute(
      "title",
      "A Python SDK job is running — the shared layout is frozen until it finishes.",
    );
    expect(within(payments).queryByRole("button", { name: "Confirm layout" })).toBeNull();
    expect(endpointRow("List payments")).toHaveAttribute("draggable", "false");
  });

  it("says why an edit was refused, and shows the layout as it is", async () => {
    // the page believes invoices is free and unconfirmed; the mock has it in review
    const stale = generationResources("billing-api").map((r) =>
      r.id === "v1_invoices" ? { ...r, confirmedBy: null, confirmedAt: null, jobs: {} } : r,
    );
    layoutPage("/generation/billing-api/layout", [[keys.genResources("billing-api"), stale]]);

    const invoices = (await screen.findAllByRole("group", { name: "invoices" }))[0];
    fireEvent.click(button(invoices, "Confirm layout"));

    expect(await screen.findByText("That did not go through")).toBeInTheDocument();
    expect(
      screen.getByText("The layout of invoices is frozen: it is generating, in review or merged"),
    ).toBeInTheDocument();
    expect(await within(resource("v1", "invoices")).findByText("in review · Python SDK")).toBeInTheDocument();
    expect(screen.queryByText("Layout edited · saved on the service")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    // the query client hands the reset on in its next tick
    await waitFor(() => expect(screen.queryByText("That did not go through")).toBeNull());
  });
});
