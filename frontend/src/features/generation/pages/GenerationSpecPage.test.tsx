import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router";
import { renderPage } from "../../../test/render";
import { tokenWithRoles } from "../../../test/token";
import {
  chooseType,
  confirmResource,
  generationResources,
  generationSpec,
  resetGenerationMock,
  startGeneration,
} from "../data/mock";
import { GenerationLayoutPage } from "./GenerationLayoutPage";
import { GenerationListPage } from "./GenerationListPage";
import { GenerationServicePage } from "./GenerationServicePage";
import { GenerationSpecPage } from "./GenerationSpecPage";

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

/* The mock lives in module memory, and the choices and generations below change it. */
beforeEach(() => {
  resetGenerationMock();
  session.token = tokenWithRoles("worker");
});

/** Where the page navigated to. */
function Location() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}

function specPage(path = "/generation/billing-api/spec/v1/v1_invoices") {
  return renderPage(
    <>
      <GenerationSpecPage />
      <Location />
    </>,
    { path, route: "/generation/:name/spec/:version/:resource" },
  );
}

const location = () => screen.getByTestId("location").textContent;
const cls = (name: string) => screen.getByRole("region", { name });
const field = (clsName: string, name: string) => within(cls(clsName)).getByRole("group", { name });
const operation = (title: string) => screen.getByRole("group", { name: title });
const generateButton = () => screen.getByRole("button", { name: /^Generate for / });
const noGenerateButton = () => expect(screen.queryByRole("button", { name: /^Generate for / })).toBeNull();
/** Open the problem of a field, by the tag it carries. */
const openProblem = (clsName: string, name: string, tag: string) =>
  fireEvent.click(within(field(clsName, name)).getByRole("button", { name: tag }));
/** The button offering a type for a field's problem. */
const option = (clsName: string, name: string, type: string) =>
  within(field(clsName, name)).getByText(type, { selector: "button > span" }).closest("button") as HTMLElement;

describe("the spec of invoices v1 on the in-memory mock", () => {
  it("shows the operations, the classes, the fields left to decide and the job in review, with no dependencies block", async () => {
    specPage();

    expect(screen.getByText("Loading service…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "billing_api.invoices" })).toBeInTheDocument();
    expect(screen.getByText("confirmed")).toBeInTheDocument();
    expect(
      screen.getByText("Generation spec · Python SDK · v1 · 4 operations · 4 base · 0 custom · 2 classes"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "billing-api layout" })).toHaveAttribute("href", "/generation/billing-api");

    const list = operation("List invoices of a project");
    expect(within(list).getByText("base")).toBeInTheDocument();
    expect(within(list).getByText("GET")).toBeInTheDocument();
    expect(within(list).getByText("/v1/billing/invoices")).toBeInTheDocument();
    expect(within(list).getByText("invoices.list()")).toBeInTheDocument();
    expect(within(list).getByTitle("Open this document in the repository at the scanned commit")).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/billing-api/blob/mockcommit/api-ref/source/invoices/list-invoices.rst",
    );
    expect(within(operation("Query invoice details")).getByText("invoices.get()")).toBeInTheDocument();
    expect(within(operation("Create a manual invoice")).getByText("invoices.create()")).toBeInTheDocument();
    expect(within(operation("Cancel an invoice")).getByText("invoices.delete()")).toBeInTheDocument();

    expect(within(cls("Invoice")).getByText("5 fields")).toBeInTheDocument();
    expect(within(cls("Invoice")).getByText("2 to decide")).toBeInTheDocument();
    expect(within(cls("InvoiceItem")).getByText("3 fields")).toBeInTheDocument();
    expect(within(cls("InvoiceItem")).queryByText(/to decide/)).toBeNull();

    const amount = field("Invoice", "amount");
    expect(within(amount).getByText("Integer")).toBeInTheDocument();
    expect(within(amount).getByText("yes")).toBeInTheDocument();
    expect(within(amount).getByRole("button", { name: "type conflict" })).toHaveAttribute(
      "title",
      "Conflict: the create page documents this field as String, the get page as Integer. Pick the type the SDK should use before generating.",
    );
    const items = field("Invoice", "items");
    expect(within(items).getByText("⚠ Unknown")).toBeInTheDocument();
    expect(within(items).getByText("—")).toBeInTheDocument();
    expect(within(items).getByRole("button", { name: "unknown type" })).toBeInTheDocument();
    expect(within(field("Invoice", "created_at")).queryByRole("button")).toBeNull();
    // nothing is open until a problem is clicked
    expect(screen.queryByText("Use this type")).toBeNull();

    // generated on Python SDK already: its job stands in place of Generate, as on the card, and leads to the result
    expect(screen.getByRole("link", { name: "in review · PR 131" })).toHaveAttribute(
      "href",
      "/generation/billing-api/result/v1/v1_invoices",
    );
    noGenerateButton();
    expect(screen.queryByText(/^decide the/)).toBeNull();
    expect(screen.queryByText(/Dependencies/)).toBeNull();
  });

  it("opens a type conflict, records who chose a type and when, and takes the choice back", async () => {
    specPage();

    await screen.findByRole("heading", { name: "billing_api.invoices" });
    openProblem("Invoice", "amount", "type conflict");

    const amount = field("Invoice", "amount");
    expect(within(amount).getByText(/^Conflict: the create page/)).toBeInTheDocument();
    expect(within(amount).getByRole("link", { name: "create-invoice.rst" })).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/billing-api/blob/mockcommit/api-ref/source/invoices/create-invoice.rst",
    );
    expect(within(amount).getByRole("link", { name: "show-invoice.rst" })).toBeInTheDocument();
    expect(within(amount).getByText("Use this type")).toBeInTheDocument();
    expect(option("Invoice", "amount", "Integer")).toHaveTextContent("as in show-invoice.rst");
    expect(option("Invoice", "amount", "String")).toHaveAttribute("aria-pressed", "false");
    expect(within(amount).queryByRole("button", { name: "Clear choice" })).toBeNull();

    fireEvent.click(option("Invoice", "amount", "String"));

    expect(await within(field("Invoice", "amount")).findByRole("button", { name: "resolved" })).toBeInTheDocument();
    expect(option("Invoice", "amount", "String")).toHaveAttribute("aria-pressed", "true");
    expect(within(field("Invoice", "amount")).getByTitle("String")).toBeInTheDocument();
    expect(
      within(field("Invoice", "amount")).getByText(/^chosen by ada@otc\.test · \d\d\/\d\d\/\d{4}, \d\d:\d\d$/),
    ).toBeInTheDocument();
    expect(within(cls("Invoice")).getByText("1 to decide")).toBeInTheDocument();

    const recorded = generationSpec("billing-api", "v1_invoices").classes[0].fields.find((f) => f.name === "amount");
    expect(recorded?.issue?.choice?.type).toBe("String");
    expect(recorded?.issue?.choice?.by).toBe("ada@otc.test");
    expect(Date.now() - Date.parse(recorded?.issue?.choice?.at ?? "")).toBeLessThan(60_000);

    fireEvent.click(within(field("Invoice", "amount")).getByRole("button", { name: "Clear choice" }));

    expect(await within(field("Invoice", "amount")).findByRole("button", { name: "type conflict" })).toBeInTheDocument();
    expect(within(field("Invoice", "amount")).queryByText(/^chosen by/)).toBeNull();
    expect(within(field("Invoice", "amount")).getByTitle("Integer")).toBeInTheDocument();
    expect(within(cls("Invoice")).getByText("2 to decide")).toBeInTheDocument();
    expect(generationSpec("billing-api", "v1_invoices").classes[0].fields[2].issue?.choice).toBeNull();
  });

  it("changes a choice, takes it back by choosing it again, and keeps one problem open at a time", async () => {
    specPage();

    await screen.findByRole("heading", { name: "billing_api.invoices" });
    openProblem("Invoice", "items", "unknown type");
    fireEvent.click(option("Invoice", "items", "List[String]"));
    expect(await within(field("Invoice", "items")).findByTitle("List[String]")).toBeInTheDocument();
    expect(within(field("Invoice", "items")).queryByText("⚠ Unknown")).toBeNull();

    fireEvent.click(option("Invoice", "items", "List[InvoiceItem]"));
    expect(await within(field("Invoice", "items")).findByTitle("List[InvoiceItem]")).toBeInTheDocument();
    expect(option("Invoice", "items", "List[String]")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(option("Invoice", "items", "List[InvoiceItem]"));
    expect(await within(field("Invoice", "items")).findByText("⚠ Unknown")).toBeInTheDocument();

    openProblem("Invoice", "amount", "type conflict");
    expect(screen.getAllByText("Use this type")).toHaveLength(1);
    expect(within(field("Invoice", "amount")).getByText("Use this type")).toBeInTheDocument();

    openProblem("Invoice", "amount", "type conflict");
    expect(screen.queryByText("Use this type")).toBeNull();
  });

  it("holds Generate until every field is decided, and says why it is refused when someone generated meanwhile", async () => {
    confirmResource("billing-api", "v1_payments", "valeriia");
    specPage("/generation/billing-api/spec/v1/v1_payments");

    await screen.findByRole("heading", { name: "billing_api.payments" });
    expect(generateButton()).toBeDisabled();
    expect(screen.getByText("decide the highlighted field first")).toBeInTheDocument();

    openProblem("Payment", "method", "unknown type");
    fireEvent.click(option("Payment", "method", "String"));
    await within(field("Payment", "method")).findByRole("button", { name: "resolved" });

    expect(generateButton()).toBeEnabled();
    expect(screen.queryByText(/^decide the/)).toBeNull();
    expect(within(cls("Payment")).queryByText(/to decide/)).toBeNull();

    // someone starts it elsewhere before this page has heard of it
    startGeneration("billing-api", "v1_payments", "python");
    fireEvent.click(generateButton());

    expect(await screen.findByText("That did not go through")).toBeInTheDocument();
    expect(screen.getByText("payments is generating on Python SDK")).toBeInTheDocument();
    expect(location()).toBe("/generation/billing-api/spec/v1/v1_payments");
    // with the refusal the page hears of that job, and shows it in place of Generate
    expect(await screen.findByRole("link", { name: "generating" })).toHaveAttribute(
      "href",
      "/generation/billing-api/result/v1/v1_payments",
    );
    noGenerateButton();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(screen.queryByText("That did not go through")).toBeNull());
  });

  it("works on the target in the address, holds Generate there as the card does, and keeps the target on the way back", async () => {
    specPage("/generation/billing-api/spec/v1/v1_invoices?target=ansible");

    expect(
      await screen.findByText("Generation spec · Ansible modules · v1 · 4 operations · 4 base · 0 custom · 2 classes"),
    ).toBeInTheDocument();
    expect(generateButton()).toHaveTextContent("Generate for Ansible modules");
    expect(generateButton()).toBeDisabled();
    // the card's reason comes first; the two open fields are not the one named
    expect(screen.getByText("waits on Python SDK")).toBeInTheDocument();
    expect(screen.queryByText(/^decide the/)).toBeNull();
    // Python SDK's job is not this target's
    expect(screen.queryByRole("link", { name: /in review/ })).toBeNull();
    expect(screen.getByRole("link", { name: "billing-api layout" })).toHaveAttribute(
      "href",
      "/generation/billing-api?target=ansible",
    );
  });
});

describe("a viewer", () => {
  beforeEach(() => {
    session.token = tokenWithRoles("viewer");
  });

  it("reads the problems, the choices and the job, but is offered no way to decide", async () => {
    specPage();

    await screen.findByRole("heading", { name: "billing_api.invoices" });
    openProblem("Invoice", "amount", "type conflict");

    const amount = field("Invoice", "amount");
    expect(within(amount).getByText("Use this type")).toBeInTheDocument();
    expect(within(amount).getByText("as in show-invoice.rst")).toBeInTheDocument();
    // the tag that opened the problem is the only button left in the field
    expect(within(amount).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "in review · PR 131" })).toBeInTheDocument();
  });

  it("reads why a resource cannot be generated, and is offered no Generate once nothing holds it", async () => {
    const { unmount } = specPage("/generation/billing-api/spec/v1/v1_payments");

    expect(await screen.findByText("confirm the layout first")).toBeInTheDocument();
    noGenerateButton();
    unmount();

    confirmResource("billing-api", "v1_payments", "valeriia");
    chooseType("billing-api", "v1_payments", "Payment", "method", "String", "valeriia");
    specPage("/generation/billing-api/spec/v1/v1_payments");

    await screen.findByRole("heading", { name: "billing_api.payments" });
    expect(within(field("Payment", "method")).getByTitle("String")).toBeInTheDocument();
    expect(screen.queryByText(/first$/)).toBeNull();
    noGenerateButton();
  });
});

describe("other resources on the mock", () => {
  it("makes a custom action of an operation that is not base CRUD, and names a class after a resource with none prepared", async () => {
    specPage("/generation/billing-api/spec/v2/v2_invoices");

    expect(
      await screen.findByText("Generation spec · Python SDK · v2 · 2 operations · 1 base · 1 custom · 1 class"),
    ).toBeInTheDocument();
    expect(screen.getByText("new")).toBeInTheDocument();
    const exportOp = operation("Export invoices as CSV");
    expect(within(exportOp).getByText("custom")).toBeInTheDocument();
    expect(within(exportOp).getByText("invoices.export()")).toBeInTheDocument();
    expect(within(operation("List invoices (v2)")).getByText("invoices.list()")).toBeInTheDocument();
    expect(within(cls("Invoice")).getByText("3 fields")).toBeInTheDocument();
    expect(generateButton()).toBeDisabled();
  });

  it("holds Generate for a resource whose layout is not confirmed, before its open fields, and leads to the layout", async () => {
    specPage("/generation/billing-api/spec/v1/v1_payments");

    expect(await screen.findByText("confirm the layout first")).toBeInTheDocument();
    expect(within(cls("Payment")).getByText("1 to decide")).toBeInTheDocument();
    expect(screen.queryByText(/^decide the/)).toBeNull();
    expect(generateButton()).toBeDisabled();
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute("href", "/generation/billing-api/layout");
  });

  it("shows a failed job in place of Generate, leading to its result", async () => {
    specPage("/generation/customer-core/spec/v1/c_contacts");

    expect(await screen.findByRole("heading", { name: "customer_core.contacts" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "failed" })).toHaveAttribute(
      "href",
      "/generation/customer-core/result/v1/c_contacts",
    );
    noGenerateButton();
    expect(screen.queryByText("confirm the layout first")).toBeNull();
  });

  it("is backed by a mock that refuses what the page would not offer, and keeps the job it would replace", () => {
    expect(() => startGeneration("billing-api", "v1_invoices", "python")).toThrow("invoices is in review on Python SDK");
    expect(generationResources("billing-api").find((r) => r.id === "v1_invoices")?.jobs.python).toEqual({
      status: "done",
      pr: 131,
    });
    expect(() => startGeneration("billing-api", "v2_invoices", "python")).toThrow(
      "invoices cannot be generated for Python SDK: its layout is not confirmed",
    );
    expect(() => startGeneration("billing-api", "v1_invoices", "ansible")).toThrow(
      "invoices cannot be generated for Ansible modules: it is not merged in Python SDK yet",
    );
    confirmResource("billing-api", "v1_payments", "valeriia");
    expect(() => startGeneration("billing-api", "v1_payments", "python")).toThrow(
      "payments cannot be generated: 1 field(s) still to decide",
    );
    expect(generationResources("billing-api").find((r) => r.id === "v1_payments")?.jobs).toEqual({});
  });

  it("does not open a resource the service does not have, nor one under another version", async () => {
    const { unmount } = specPage("/generation/billing-api/spec/v1/v9_nothing");

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "billing-api layout" })).toHaveAttribute("href", "/generation/billing-api");
    unmount();

    specPage("/generation/billing-api/spec/v2/v1_invoices");
    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
  });

  it("does not open a service that is not in Generation", async () => {
    specPage("/generation/sms-gateway/spec/v1/v1_invoices");

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
  });
});

describe("the way in and out", () => {
  /** The list, the card, the layout and the spec under their own routes, so each can be left for the next. */
  function panel(path: string) {
    return renderPage(
      <>
        <Routes>
          <Route path="generation" element={<GenerationListPage />} />
          <Route path="generation/:name" element={<GenerationServicePage />} />
          <Route path="generation/:name/layout" element={<GenerationLayoutPage />} />
          <Route path="generation/:name/spec/:version/:resource" element={<GenerationSpecPage />} />
        </Routes>
        <Location />
      </>,
      { path, route: "*" },
    );
  }

  it("confirms payments, opens its spec from the card, decides its field and starts the generation", async () => {
    panel("/generation/billing-api/layout");

    const v1 = await screen.findByRole("region", { name: "v1" });
    fireEvent.click(within(within(v1).getByRole("group", { name: "payments" })).getByRole("button", { name: "Confirm layout" }));
    await within(within(v1).getByRole("group", { name: "payments" })).findByText("confirmed");
    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);
    fireEvent.click(await screen.findByRole("link", { name: "Generate" }));

    expect(location()).toBe("/generation/billing-api/spec/v1/v1_payments");
    expect(await screen.findByRole("heading", { name: "billing_api.payments" })).toBeInTheDocument();
    expect(
      screen.getByText("Generation spec · Python SDK · v1 · 3 operations · 3 base · 0 custom · 1 class"),
    ).toBeInTheDocument();
    expect(generateButton()).toBeDisabled();
    expect(screen.getByText("decide the highlighted field first")).toBeInTheDocument();

    openProblem("Payment", "method", "unknown type");
    fireEvent.click(option("Payment", "method", "Enum[PaymentMethod]"));
    await within(field("Payment", "method")).findByRole("button", { name: "resolved" });
    fireEvent.click(generateButton());

    await waitFor(() => expect(location()).toBe("/generation/billing-api/result/v1/v1_payments"));
    expect(generationResources("billing-api").find((r) => r.id === "v1_payments")?.jobs.python).toEqual({
      status: "running",
      pr: null,
    });
  });

  it("leads back to the card", async () => {
    panel("/generation/billing-api/spec/v1/v1_invoices");

    fireEvent.click(await screen.findByRole("link", { name: "billing-api layout" }));

    expect(location()).toBe("/generation/billing-api");
    expect(await screen.findByRole("link", { name: "in review · PR 131" })).toBeInTheDocument();
  });

  it("carries the list's chip and search from the card into the spec, and back", async () => {
    confirmResource("billing-api", "v1_payments", "valeriia");
    panel("/generation?filter=review");

    fireEvent.change(await screen.findByPlaceholderText("Filter services…"), { target: { value: "billing" } });
    fireEvent.click(screen.getByText("billing-api"));
    fireEvent.click(await screen.findByRole("link", { name: "Generate" }));
    fireEvent.click(await screen.findByRole("link", { name: "billing-api layout" }));

    expect(location()).toBe("/generation/billing-api");
    expect(await screen.findByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation?filter=review");
  });
});
