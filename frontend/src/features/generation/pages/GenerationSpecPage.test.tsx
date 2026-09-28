import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router";
import { renderPage } from "../../../test/render";
import { tokenWithRoles } from "../../../test/token";
import {
  chooseType,
  confirmResource,
  generationResources,
  generationServices,
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
/** The job Generate starts: the first numbered after the seed, running, by the signed-in user, no pull request yet. */
const startedJob = {
  id: 2101,
  status: "running",
  pr: null,
  startedBy: "ada@otc.test",
  startedAt: expect.any(String),
  mergedBy: null,
  mergedAt: null,
  error: null,
};
/** The mock records when a job started; the page does not send it. */
const expectJustNow = (service: string, resource: string) => {
  const job = generationResources(service).find((r) => r.id === resource)?.jobs.python;
  expect(Date.now() - Date.parse(job?.startedAt ?? "")).toBeLessThan(60_000);
};
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
  it("shows the operations, the classes, the fields decided before it was generated and the job in review, with no dependencies block", async () => {
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
    // it is generated already, so both its problems were decided first
    expect(within(cls("Invoice")).queryByText(/to decide/)).toBeNull();
    expect(within(cls("InvoiceItem")).getByText("3 fields")).toBeInTheDocument();
    expect(within(cls("InvoiceItem")).queryByText(/to decide/)).toBeNull();

    const amount = field("Invoice", "amount");
    expect(within(amount).getByTitle("Integer")).toBeInTheDocument();
    expect(within(amount).getByText("yes")).toBeInTheDocument();
    expect(within(amount).getByRole("button", { name: "resolved" })).toHaveAttribute(
      "title",
      "Conflict: the create page documents this field as String, the get page as Integer. Pick the type the SDK should use before generating.",
    );
    const items = field("Invoice", "items");
    expect(within(items).getByTitle("List[InvoiceItem]")).toBeInTheDocument();
    expect(within(items).queryByText("⚠ Unknown")).toBeNull();
    expect(within(items).getByText("—")).toBeInTheDocument();
    expect(within(items).getByRole("button", { name: "resolved" })).toBeInTheDocument();
    expect(within(field("Invoice", "created_at")).queryByRole("button")).toBeNull();
    // nothing is open until a problem is clicked
    expect(screen.queryByText("Use this type")).toBeNull();

    openProblem("Invoice", "items", "resolved");
    expect(option("Invoice", "items", "List[InvoiceItem]")).toHaveAttribute("aria-pressed", "true");
    expect(
      within(field("Invoice", "items")).getByText(/^chosen by valeriia · \d\d\/\d\d\/2026, \d\d:\d\d$/),
    ).toBeInTheDocument();
    // the day on screen is the viewer's; the moment, before the generation started, is the data's
    expect(
      generationSpec("billing-api", "v1_invoices").classes[0].fields.find((f) => f.name === "items")?.issue?.choice,
    ).toEqual({ type: "List[InvoiceItem]", by: "valeriia", at: "2026-08-11T14:15:00Z" });

    // generated on Python SDK already: its job stands in place of Generate, as on the card, and leads to the result
    expect(screen.getByRole("link", { name: "in review · PR 131" })).toHaveAttribute(
      "href",
      "/generation/billing-api/result/v1/v1_invoices",
    );
    noGenerateButton();
    expect(screen.queryByText(/^decide the/)).toBeNull();
    expect(screen.queryByText(/Dependencies/)).toBeNull();
  });

  it("opens a type conflict, takes the choice back, and records who chose a type and when", async () => {
    specPage();

    await screen.findByRole("heading", { name: "billing_api.invoices" });
    openProblem("Invoice", "amount", "resolved");

    const amount = field("Invoice", "amount");
    expect(within(amount).getByText(/^Conflict: the create page/)).toBeInTheDocument();
    expect(within(amount).getByRole("link", { name: "create-invoice.rst" })).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/billing-api/blob/mockcommit/api-ref/source/invoices/create-invoice.rst",
    );
    expect(within(amount).getByRole("link", { name: "show-invoice.rst" })).toBeInTheDocument();
    expect(within(amount).getByText("Use this type")).toBeInTheDocument();
    expect(option("Invoice", "amount", "Integer")).toHaveTextContent("as in show-invoice.rst");
    expect(option("Invoice", "amount", "Integer")).toHaveAttribute("aria-pressed", "true");
    expect(within(amount).getByText(/^chosen by valeriia · \d\d\/\d\d\/2026, \d\d:\d\d$/)).toBeInTheDocument();
    expect(
      generationSpec("billing-api", "v1_invoices").classes[0].fields.find((f) => f.name === "amount")?.issue?.choice,
    ).toEqual({ type: "Integer", by: "valeriia", at: "2026-08-11T14:12:00Z" });

    fireEvent.click(within(amount).getByRole("button", { name: "Clear choice" }));

    expect(await within(field("Invoice", "amount")).findByRole("button", { name: "type conflict" })).toBeInTheDocument();
    expect(within(field("Invoice", "amount")).queryByText(/^chosen by/)).toBeNull();
    expect(within(field("Invoice", "amount")).queryByRole("button", { name: "Clear choice" })).toBeNull();
    expect(option("Invoice", "amount", "Integer")).toHaveAttribute("aria-pressed", "false");
    expect(option("Invoice", "amount", "String")).toHaveAttribute("aria-pressed", "false");
    expect(within(field("Invoice", "amount")).getByTitle("Integer")).toBeInTheDocument();
    expect(within(cls("Invoice")).getByText("1 to decide")).toBeInTheDocument();
    expect(generationSpec("billing-api", "v1_invoices").classes[0].fields[2].issue?.choice).toBeNull();

    fireEvent.click(option("Invoice", "amount", "String"));

    expect(await within(field("Invoice", "amount")).findByRole("button", { name: "resolved" })).toBeInTheDocument();
    expect(option("Invoice", "amount", "String")).toHaveAttribute("aria-pressed", "true");
    expect(within(field("Invoice", "amount")).getByTitle("String")).toBeInTheDocument();
    expect(
      within(field("Invoice", "amount")).getByText(/^chosen by ada@otc\.test · \d\d\/\d\d\/\d{4}, \d\d:\d\d$/),
    ).toBeInTheDocument();
    expect(within(cls("Invoice")).queryByText(/to decide/)).toBeNull();

    const recorded = generationSpec("billing-api", "v1_invoices").classes[0].fields.find((f) => f.name === "amount");
    expect(recorded?.issue?.choice?.type).toBe("String");
    expect(recorded?.issue?.choice?.by).toBe("ada@otc.test");
    expect(Date.now() - Date.parse(recorded?.issue?.choice?.at ?? "")).toBeLessThan(60_000);
  });

  it("changes a choice, takes it back by choosing it again, and keeps one problem open at a time", async () => {
    specPage();

    await screen.findByRole("heading", { name: "billing_api.invoices" });
    openProblem("Invoice", "items", "resolved");
    fireEvent.click(option("Invoice", "items", "List[String]"));
    expect(await within(field("Invoice", "items")).findByTitle("List[String]")).toBeInTheDocument();
    expect(option("Invoice", "items", "List[InvoiceItem]")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(option("Invoice", "items", "List[InvoiceItem]"));
    expect(await within(field("Invoice", "items")).findByTitle("List[InvoiceItem]")).toBeInTheDocument();
    expect(option("Invoice", "items", "List[String]")).toHaveAttribute("aria-pressed", "false");
    expect(within(field("Invoice", "items")).queryByText("⚠ Unknown")).toBeNull();

    fireEvent.click(option("Invoice", "items", "List[InvoiceItem]"));
    expect(await within(field("Invoice", "items")).findByText("⚠ Unknown")).toBeInTheDocument();
    expect(within(field("Invoice", "items")).getByRole("button", { name: "unknown type" })).toBeInTheDocument();

    openProblem("Invoice", "amount", "resolved");
    expect(screen.getAllByText("Use this type")).toHaveLength(1);
    expect(within(field("Invoice", "amount")).getByText("Use this type")).toBeInTheDocument();

    openProblem("Invoice", "amount", "resolved");
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
    startGeneration("billing-api", "v1_payments", "python", "valeriia");
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

  it("says why Generate is refused when someone took a choice back meanwhile, and shows the field to decide", async () => {
    confirmResource("billing-api", "v1_payments", "valeriia");
    chooseType("billing-api", "v1_payments", "Payment", "method", "String", "valeriia");
    specPage("/generation/billing-api/spec/v1/v1_payments");

    await screen.findByRole("heading", { name: "billing_api.payments" });
    expect(within(field("Payment", "method")).getByRole("button", { name: "resolved" })).toBeInTheDocument();
    expect(generateButton()).toBeEnabled();

    // someone takes the choice back elsewhere before this page has heard of it
    chooseType("billing-api", "v1_payments", "Payment", "method", null, "valeriia");
    fireEvent.click(generateButton());

    expect(await screen.findByText("payments cannot be generated: 1 field(s) still to decide")).toBeInTheDocument();
    // with the refusal the page hears of it: the field is open again, and it holds Generate
    expect(await within(field("Payment", "method")).findByRole("button", { name: "unknown type" })).toBeInTheDocument();
    expect(within(cls("Payment")).getByText("1 to decide")).toBeInTheDocument();
    expect(generateButton()).toBeDisabled();
    expect(screen.getByText("decide the highlighted field first")).toBeInTheDocument();
    expect(location()).toBe("/generation/billing-api/spec/v1/v1_payments");
    expect(generationResources("billing-api").find((r) => r.id === "v1_payments")?.jobs).toEqual({});
  });

  it("works on the target in the address, holds Generate there as the card does, and keeps the target on the way back", async () => {
    chooseType("billing-api", "v1_invoices", "Invoice", "amount", null, "valeriia");
    specPage("/generation/billing-api/spec/v1/v1_invoices?target=ansible");

    expect(
      await screen.findByText("Generation spec · Ansible modules · v1 · 4 operations · 4 base · 0 custom · 2 classes"),
    ).toBeInTheDocument();
    expect(within(cls("Invoice")).getByText("1 to decide")).toBeInTheDocument();
    expect(generateButton()).toHaveTextContent("Generate for Ansible modules");
    expect(generateButton()).toBeDisabled();
    // the card's reason comes first; the open field is not the one named
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

describe("the spec of payments v1 on the in-memory mock", () => {
  it("shows a field of unknown type left to decide, what the docs say of it and the types to choose from", async () => {
    specPage("/generation/billing-api/spec/v1/v1_payments");

    expect(await screen.findByRole("heading", { name: "billing_api.payments" })).toBeInTheDocument();
    expect(screen.getByText("auto")).toBeInTheDocument();
    expect(
      screen.getByText("Generation spec · Python SDK · v1 · 3 operations · 3 base · 0 custom · 1 class"),
    ).toBeInTheDocument();
    expect(within(operation("List payments")).getByText("payments.list()")).toBeInTheDocument();
    expect(within(operation("Submit a payment")).getByText("payments.create()")).toBeInTheDocument();
    expect(within(operation("Update payment method")).getByText("payments.update()")).toBeInTheDocument();

    expect(within(cls("Payment")).getByText("4 fields")).toBeInTheDocument();
    expect(within(cls("Payment")).getByText("1 to decide")).toBeInTheDocument();

    const method = field("Payment", "method");
    expect(within(method).getByText("⚠ Unknown")).toHaveClass("text-amber-700");
    expect(within(method).getByText("yes")).toBeInTheDocument();
    expect(within(method).getByText("Payment method")).toBeInTheDocument();
    expect(within(method).getByRole("button", { name: "unknown type" })).toHaveAttribute(
      "title",
      "Type not recognized — the table cell reads “enum (see below)” and the values are only in prose. Choose an enum or a plain string.",
    );
    // only the field left to decide is highlighted
    expect(method.firstElementChild).toHaveClass("bg-amber-50");
    expect(field("Payment", "invoice_id").firstElementChild).toHaveClass("bg-white");
    expect(within(field("Payment", "invoice_id")).getByTitle("String")).toBeInTheDocument();
    expect(within(field("Payment", "paid_at")).queryByRole("button")).toBeNull();

    openProblem("Payment", "method", "unknown type");
    expect(within(method).getByText(/^Type not recognized — the table cell reads/)).toBeInTheDocument();
    expect(within(method).getByRole("link", { name: "create-payment.rst" })).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/billing-api/blob/mockcommit/api-ref/source/payments/create-payment.rst",
    );
    expect(option("Payment", "method", "Enum[PaymentMethod]")).toHaveTextContent(
      "values listed in the prose below the table",
    );
    expect(option("Payment", "method", "Enum[PaymentMethod]")).toHaveAttribute("aria-pressed", "false");
    expect(option("Payment", "method", "String")).toHaveTextContent("accept any value");
    expect(option("Payment", "method", "String")).toHaveAttribute("aria-pressed", "false");
    // nobody has chosen, so there is no one to name and nothing to take back
    expect(within(method).queryByText(/^chosen by/)).toBeNull();
    expect(within(method).queryByRole("button", { name: "Clear choice" })).toBeNull();
    expect(
      generationSpec("billing-api", "v1_payments").classes[0].fields.find((f) => f.name === "method")?.issue?.choice,
    ).toBeNull();
  });
});

describe("a viewer", () => {
  beforeEach(() => {
    session.token = tokenWithRoles("viewer");
  });

  it("reads the problems, the choices and the job, but is offered no way to decide", async () => {
    specPage();

    await screen.findByRole("heading", { name: "billing_api.invoices" });
    openProblem("Invoice", "amount", "resolved");

    const amount = field("Invoice", "amount");
    expect(within(amount).getByText("Use this type")).toBeInTheDocument();
    expect(within(amount).getByText("as in show-invoice.rst")).toBeInTheDocument();
    expect(within(amount).getByText(/^chosen by valeriia · /)).toBeInTheDocument();
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

describe("the spec of invoices v2 on the in-memory mock", () => {
  it("makes a custom action of an operation that is not base CRUD, names a class after a resource with none prepared, and asks for the layout first", async () => {
    specPage("/generation/billing-api/spec/v2/v2_invoices");

    expect(await screen.findByRole("heading", { name: "billing_api.invoices" })).toBeInTheDocument();
    // from the new docs and not confirmed yet
    expect(screen.getByText("new")).toBeInTheDocument();
    expect(
      screen.getByText("Generation spec · Python SDK · v2 · 2 operations · 1 base · 1 custom · 1 class"),
    ).toBeInTheDocument();

    const list = operation("List invoices (v2)");
    expect(within(list).getByText("base")).toBeInTheDocument();
    expect(within(list).getByText("GET")).toBeInTheDocument();
    expect(within(list).getByText("/v2/billing/invoices")).toBeInTheDocument();
    expect(within(list).getByText("invoices.list()")).toBeInTheDocument();
    const exportOp = operation("Export invoices as CSV");
    expect(within(exportOp).getByText("custom")).toBeInTheDocument();
    expect(within(exportOp).getByText("POST")).toBeInTheDocument();
    expect(within(exportOp).getByText("/v2/billing/invoices/export")).toBeInTheDocument();
    expect(within(exportOp).getByText("invoices.export()")).toBeInTheDocument();
    expect(within(exportOp).getByTitle("Open this document in the repository at the scanned commit")).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/billing-api/blob/mockcommit/api-ref/source/v2/invoices/export-invoices.rst",
    );

    // no classes prepared for it, so the one the prototype falls back on: named after the resource, nothing to decide
    expect(within(cls("Invoice")).getByText("3 fields")).toBeInTheDocument();
    expect(within(cls("Invoice")).queryByText(/to decide/)).toBeNull();
    const id = field("Invoice", "id");
    expect(within(id).getByTitle("String")).toBeInTheDocument();
    expect(within(id).getByText("yes")).toBeInTheDocument();
    expect(within(id).getByText("Resource ID")).toBeInTheDocument();
    const name = field("Invoice", "name");
    expect(within(name).getByTitle("String")).toBeInTheDocument();
    expect(within(name).getByText("—")).toBeInTheDocument();
    expect(within(name).getByText("Human-readable name")).toBeInTheDocument();
    const createdAt = field("Invoice", "created_at");
    expect(within(createdAt).getByTitle("DateTime")).toBeInTheDocument();
    expect(within(createdAt).getByText("Creation timestamp")).toBeInTheDocument();
    for (const f of [id, name, createdAt]) {
      expect(f.firstElementChild).toHaveClass("bg-white");
      expect(within(f).queryByRole("button")).toBeNull();
    }

    // never generated: only the layout holds it
    expect(screen.queryByRole("link", { name: /in review|generating|merged|failed/ })).toBeNull();
    expect(generateButton()).toBeDisabled();
    expect(screen.getByText("confirm the layout first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute("href", "/generation/billing-api/layout");
    expect(screen.queryByText(/^decide the/)).toBeNull();
  });

  it("is offered for generation as soon as its layout is confirmed, and on Ansible modules waits on Python SDK", async () => {
    confirmResource("billing-api", "v2_invoices", "valeriia");
    const { unmount } = specPage("/generation/billing-api/spec/v2/v2_invoices?target=ansible");

    expect(await screen.findByText("waits on Python SDK")).toBeInTheDocument();
    expect(generateButton()).toHaveTextContent("Generate for Ansible modules");
    expect(generateButton()).toBeDisabled();
    unmount();

    specPage("/generation/billing-api/spec/v2/v2_invoices");

    expect(await screen.findByRole("heading", { name: "billing_api.invoices" })).toBeInTheDocument();
    expect(screen.getByText("confirmed")).toBeInTheDocument();
    expect(screen.queryByText(/first$/)).toBeNull();
    expect(generateButton()).toBeEnabled();

    fireEvent.click(generateButton());

    await waitFor(() =>
      expect(generationResources("billing-api").find((r) => r.id === "v2_invoices")?.jobs).toEqual({
        python: startedJob,
      }),
    );
    expectJustNow("billing-api", "v2_invoices");
  });
});

describe("the spec of addresses in customer-core on the in-memory mock", () => {
  it("makes base operations of a nested list and a PATCH on an item, names its class Address, and asks for the layout first", async () => {
    specPage("/generation/customer-core/spec/v1/c_addresses");

    expect(await screen.findByRole("heading", { name: "customer_core.addresses" })).toBeInTheDocument();
    expect(screen.getByText("new")).toBeInTheDocument();
    expect(
      screen.getByText("Generation spec · Python SDK · v1 · 2 operations · 2 base · 0 custom · 1 class"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "customer-core layout" })).toHaveAttribute(
      "href",
      "/generation/customer-core",
    );

    // a GET on a collection is a list, though the collection sits under a customer
    const list = operation("List addresses");
    expect(within(list).getByText("base")).toBeInTheDocument();
    expect(within(list).getByText("GET")).toBeInTheDocument();
    expect(within(list).getByText("/v1/customers/{customer_id}/addresses")).toBeInTheDocument();
    expect(within(list).getByText("addresses.list()")).toBeInTheDocument();
    expect(within(list).getByTitle("Open this document in the repository at the scanned commit")).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/customer-core/blob/mockcommit/api-ref/source/addresses/list-addresses.rst",
    );
    // a PATCH on an item is an update, as a PUT is
    const update = operation("Update an address");
    expect(within(update).getByText("base")).toBeInTheDocument();
    expect(within(update).getByText("PATCH")).toHaveClass("text-amber-700");
    expect(within(update).getByText("/v1/customers/{customer_id}/addresses/{address_id}")).toBeInTheDocument();
    expect(within(update).getByText("addresses.update()")).toBeInTheDocument();
    expect(within(update).getByTitle("Open this document in the repository at the scanned commit")).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/customer-core/blob/mockcommit/api-ref/source/addresses/update-address.rst",
    );

    // no classes prepared for it: the one named after the resource, "addresses" losing its "es"
    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(within(cls("Address")).getByText("3 fields")).toBeInTheDocument();
    expect(within(cls("Address")).queryByText(/to decide/)).toBeNull();
    for (const [name, type] of [
      ["id", "String"],
      ["name", "String"],
      ["created_at", "DateTime"],
    ] as const) {
      const f = field("Address", name);
      expect(within(f).getByTitle(type)).toBeInTheDocument();
      expect(f.firstElementChild).toHaveClass("bg-white");
      expect(within(f).queryByRole("button")).toBeNull();
    }

    // never generated: only the layout holds it
    expect(screen.queryByRole("link", { name: /in review|generating|merged|failed/ })).toBeNull();
    expect(generateButton()).toBeDisabled();
    expect(screen.getByText("confirm the layout first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute("href", "/generation/customer-core/layout");
    expect(screen.queryByText(/^decide the/)).toBeNull();
  });

  it("is offered for generation once its layout is confirmed, and its job puts customer-core in progress over the failed one", async () => {
    confirmResource("customer-core", "c_addresses", "valeriia");
    const { unmount } = specPage("/generation/customer-core/spec/v1/c_addresses?target=ansible");

    expect(await screen.findByText("waits on Python SDK")).toBeInTheDocument();
    expect(generateButton()).toHaveTextContent("Generate for Ansible modules");
    expect(generateButton()).toBeDisabled();
    unmount();

    specPage("/generation/customer-core/spec/v1/c_addresses");

    expect(await screen.findByRole("heading", { name: "customer_core.addresses" })).toBeInTheDocument();
    expect(screen.getByText("confirmed")).toBeInTheDocument();
    expect(screen.queryByText(/first$/)).toBeNull();

    fireEvent.click(generateButton());

    await waitFor(() =>
      expect(generationResources("customer-core").find((r) => r.id === "c_addresses")?.jobs).toEqual({
        python: startedJob,
      }),
    );
    expectJustNow("customer-core", "c_addresses");
    // the failed contacts is still failed; a running job ranks above it, and customers stays merged
    expect(generationResources("customer-core").find((r) => r.id === "c_contacts")?.jobs.python?.status).toBe("failed");
    expect(generationServices().find((s) => s.name === "customer-core")?.targets.python).toEqual({
      state: "in_progress",
      merged: 1,
      total: 3,
    });
  });
});

describe("the spec of subscriptions in notifications-hub on the in-memory mock", () => {
  it("makes base operations of a list and a create, names its class Subscription, and asks for the layout first", async () => {
    specPage("/generation/notifications-hub/spec/v1/n_subscriptions");

    expect(await screen.findByRole("heading", { name: "notifications_hub.subscriptions" })).toBeInTheDocument();
    // laid out by the scanner and not confirmed yet
    expect(screen.getByText("auto")).toBeInTheDocument();
    expect(
      screen.getByText("Generation spec · Python SDK · v1 · 2 operations · 2 base · 0 custom · 1 class"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "notifications-hub layout" })).toHaveAttribute(
      "href",
      "/generation/notifications-hub",
    );

    const list = operation("List subscriptions");
    expect(within(list).getByText("base")).toBeInTheDocument();
    expect(within(list).getByText("GET")).toBeInTheDocument();
    expect(within(list).getByText("/v1/notifications/subscriptions")).toBeInTheDocument();
    expect(within(list).getByText("subscriptions.list()")).toBeInTheDocument();
    expect(within(list).getByTitle("Open this document in the repository at the scanned commit")).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/notifications-hub/blob/mockcommit/api-ref/source/subscriptions/list-subscriptions.rst",
    );
    // a POST on the collection is a create, though its title says subscribe
    const create = operation("Subscribe to a topic");
    expect(within(create).getByText("base")).toBeInTheDocument();
    expect(within(create).getByText("POST")).toBeInTheDocument();
    expect(within(create).getByText("/v1/notifications/subscriptions")).toBeInTheDocument();
    expect(within(create).getByText("subscriptions.create()")).toBeInTheDocument();
    expect(within(create).getByTitle("Open this document in the repository at the scanned commit")).toHaveAttribute(
      "href",
      "https://github.com/opentelekomcloud-docs/notifications-hub/blob/mockcommit/api-ref/source/subscriptions/create-subscription.rst",
    );

    // no classes prepared for it: the one named after the resource, "subscriptions" losing its "s"
    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(within(cls("Subscription")).getByText("3 fields")).toBeInTheDocument();
    expect(within(cls("Subscription")).queryByText(/to decide/)).toBeNull();
    for (const [name, type, req, description] of [
      ["id", "String", "yes", "Resource ID"],
      ["name", "String", "—", "Human-readable name"],
      ["created_at", "DateTime", "—", "Creation timestamp"],
    ] as const) {
      const f = field("Subscription", name);
      expect(within(f).getByTitle(type)).toBeInTheDocument();
      expect(within(f).getByText(req)).toBeInTheDocument();
      expect(within(f).getByText(description)).toBeInTheDocument();
      expect(f.firstElementChild).toHaveClass("bg-white");
      expect(within(f).queryByRole("button")).toBeNull();
    }

    // never generated: only the layout holds it, and topics' merged job is not its own
    expect(screen.queryByRole("link", { name: /in review|generating|merged|failed/ })).toBeNull();
    expect(generateButton()).toBeDisabled();
    expect(screen.getByText("confirm the layout first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute(
      "href",
      "/generation/notifications-hub/layout",
    );
    expect(screen.queryByText(/^decide the/)).toBeNull();
    expect(screen.queryByText(/Dependencies/)).toBeNull();
  });

  it("asks for the layout first on Ansible modules too, and waits on Python SDK once it is confirmed", async () => {
    const { unmount } = specPage("/generation/notifications-hub/spec/v1/n_subscriptions?target=ansible");

    expect(
      await screen.findByText("Generation spec · Ansible modules · v1 · 2 operations · 2 base · 0 custom · 1 class"),
    ).toBeInTheDocument();
    expect(screen.getByText("confirm the layout first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute(
      "href",
      "/generation/notifications-hub/layout?target=ansible",
    );
    expect(generateButton()).toHaveTextContent("Generate for Ansible modules");
    expect(generateButton()).toBeDisabled();
    unmount();

    confirmResource("notifications-hub", "n_subscriptions", "valeriia");
    specPage("/generation/notifications-hub/spec/v1/n_subscriptions?target=ansible");

    expect(await screen.findByText("waits on Python SDK")).toBeInTheDocument();
    expect(screen.getByText("confirmed")).toBeInTheDocument();
    expect(generateButton()).toBeDisabled();
    expect(screen.getByRole("link", { name: "notifications-hub layout" })).toHaveAttribute(
      "href",
      "/generation/notifications-hub?target=ansible",
    );
  });

  it("is offered for generation once its layout is confirmed, and its job puts notifications-hub in progress", async () => {
    confirmResource("notifications-hub", "n_subscriptions", "valeriia");
    specPage("/generation/notifications-hub/spec/v1/n_subscriptions");

    expect(await screen.findByRole("heading", { name: "notifications_hub.subscriptions" })).toBeInTheDocument();
    expect(screen.getByText("confirmed")).toBeInTheDocument();
    expect(screen.queryByText(/first$/)).toBeNull();

    fireEvent.click(generateButton());

    await waitFor(() =>
      expect(generationResources("notifications-hub").find((r) => r.id === "n_subscriptions")?.jobs).toEqual({
        python: startedJob,
      }),
    );
    expectJustNow("notifications-hub", "n_subscriptions");
    // topics stays merged; the running job takes the service out of Partial, the merged count stays
    expect(generationResources("notifications-hub").find((r) => r.id === "n_topics")?.jobs.python?.status).toBe("merged");
    expect(generationServices().find((s) => s.name === "notifications-hub")?.targets.python).toEqual({
      state: "in_progress",
      merged: 1,
      total: 2,
    });
  });
});

describe("other resources on the mock", () => {
  it("holds Generate for a resource whose layout is not confirmed, before its open fields, and leads to the layout", async () => {
    specPage("/generation/billing-api/spec/v1/v1_payments");

    expect(await screen.findByText("confirm the layout first")).toBeInTheDocument();
    expect(within(cls("Payment")).getByText("1 to decide")).toBeInTheDocument();
    expect(screen.queryByText(/^decide the/)).toBeNull();
    expect(generateButton()).toBeDisabled();
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute("href", "/generation/billing-api/layout");
  });

  it("shows a merged resource with its type conflict decided before it was generated", async () => {
    specPage("/generation/customer-core/spec/v1/c_customers");

    expect(await screen.findByRole("heading", { name: "customer_core.customers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "merged · PR 122" })).toHaveAttribute(
      "href",
      "/generation/customer-core/result/v1/c_customers",
    );
    expect(within(cls("Customer")).queryByText(/to decide/)).toBeNull();
    openProblem("Customer", "active", "resolved");
    expect(option("Customer", "active", "Boolean")).toHaveAttribute("aria-pressed", "true");
    expect(
      within(field("Customer", "active")).getByText(/^chosen by ivan · \d\d\/\d\d\/2026, \d\d:\d\d$/),
    ).toBeInTheDocument();
    expect(
      generationSpec("customer-core", "c_customers").classes[0].fields.find((f) => f.name === "active")?.issue?.choice,
    ).toEqual({ type: "Boolean", by: "ivan", at: "2026-08-04T10:05:00Z" });
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
    expect(() => startGeneration("billing-api", "v1_invoices", "python", "ada")).toThrow(
      "invoices is in review on Python SDK",
    );
    expect(generationResources("billing-api").find((r) => r.id === "v1_invoices")?.jobs.python).toEqual({
      id: 2088,
      status: "done",
      pr: 131,
      startedBy: "valeriia",
      startedAt: "2026-08-11T14:20:00Z",
      mergedBy: null,
      mergedAt: null,
      error: null,
    });
    expect(() => startGeneration("billing-api", "v2_invoices", "python", "ada")).toThrow(
      "invoices cannot be generated for Python SDK: its layout is not confirmed",
    );
    expect(() => startGeneration("billing-api", "v1_invoices", "ansible", "ada")).toThrow(
      "invoices cannot be generated for Ansible modules: it is not merged in Python SDK yet",
    );
    confirmResource("billing-api", "v1_payments", "valeriia");
    expect(() => startGeneration("billing-api", "v1_payments", "python", "ada")).toThrow(
      "payments cannot be generated: 1 field(s) still to decide",
    );
    chooseType("billing-api", "v1_payments", "Payment", "method", "String", "valeriia");
    expect(() => startGeneration("billing-api", "v1_payments", "python", "")).toThrow(
      "A generation has to record who starts it",
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
    expect(generationResources("billing-api").find((r) => r.id === "v1_payments")?.jobs.python).toEqual(startedJob);
    expectJustNow("billing-api", "v1_payments");
  });

  it("confirms invoices v2, opens its spec from the card and starts the generation with nothing to decide", async () => {
    panel("/generation/billing-api/layout");

    const v2 = await screen.findByRole("region", { name: "v2" });
    fireEvent.click(within(within(v2).getByRole("group", { name: "invoices" })).getByRole("button", { name: "Confirm layout" }));
    await within(within(v2).getByRole("group", { name: "invoices" })).findByText("confirmed");
    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);
    fireEvent.click(await screen.findByRole("link", { name: "Generate" }));

    expect(location()).toBe("/generation/billing-api/spec/v2/v2_invoices");
    expect(
      await screen.findByText("Generation spec · Python SDK · v2 · 2 operations · 1 base · 1 custom · 1 class"),
    ).toBeInTheDocument();
    expect(generateButton()).toBeEnabled();
    fireEvent.click(generateButton());

    await waitFor(() => expect(location()).toBe("/generation/billing-api/result/v2/v2_invoices"));
    expect(generationResources("billing-api").find((r) => r.id === "v2_invoices")?.jobs.python).toEqual(startedJob);
  });

  it("confirms addresses in customer-core, opens its spec from the card and starts the generation", async () => {
    panel("/generation/customer-core/layout");

    const v1 = await screen.findByRole("region", { name: "v1" });
    fireEvent.click(within(within(v1).getByRole("group", { name: "addresses" })).getByRole("button", { name: "Confirm layout" }));
    await within(within(v1).getByRole("group", { name: "addresses" })).findByText("confirmed");
    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);
    // the only Generate on the card: customers is merged and contacts failed
    fireEvent.click(await screen.findByRole("link", { name: "Generate" }));

    expect(location()).toBe("/generation/customer-core/spec/v1/c_addresses");
    expect(await screen.findByRole("heading", { name: "customer_core.addresses" })).toBeInTheDocument();
    expect(
      screen.getByText("Generation spec · Python SDK · v1 · 2 operations · 2 base · 0 custom · 1 class"),
    ).toBeInTheDocument();
    expect(generateButton()).toBeEnabled();
    fireEvent.click(generateButton());

    await waitFor(() => expect(location()).toBe("/generation/customer-core/result/v1/c_addresses"));
    expect(generationResources("customer-core").find((r) => r.id === "c_addresses")?.jobs.python).toEqual(startedJob);
  });

  it("confirms subscriptions in notifications-hub, opens its spec from the card and starts the generation", async () => {
    panel("/generation/notifications-hub/layout");

    // topics is merged and left out of the editor: subscriptions is the only resource there
    const v1 = await screen.findByRole("region", { name: "v1" });
    fireEvent.click(
      within(within(v1).getByRole("group", { name: "subscriptions" })).getByRole("button", { name: "Confirm layout" }),
    );
    await within(within(v1).getByRole("group", { name: "subscriptions" })).findByText("confirmed");
    fireEvent.click(screen.getAllByRole("link", { name: "Back to generation" })[0]);
    // the only Generate on the card: topics shows its merged job
    fireEvent.click(await screen.findByRole("link", { name: "Generate" }));

    expect(location()).toBe("/generation/notifications-hub/spec/v1/n_subscriptions");
    expect(await screen.findByRole("heading", { name: "notifications_hub.subscriptions" })).toBeInTheDocument();
    expect(
      screen.getByText("Generation spec · Python SDK · v1 · 2 operations · 2 base · 0 custom · 1 class"),
    ).toBeInTheDocument();
    expect(generateButton()).toBeEnabled();
    fireEvent.click(generateButton());

    await waitFor(() => expect(location()).toBe("/generation/notifications-hub/result/v1/n_subscriptions"));
    expect(generationResources("notifications-hub").find((r) => r.id === "n_subscriptions")?.jobs.python).toEqual(
      startedJob,
    );
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
