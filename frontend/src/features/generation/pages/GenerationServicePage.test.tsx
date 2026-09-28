import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router";
import { renderPage } from "../../../test/render";
import { keys } from "../../scan/api/queries";
import { generationResources } from "../data/mock";
import type { GenResource, GenService, GenTarget } from "../data/types";
import { GenerationListPage } from "./GenerationListPage";
import { GenerationServicePage } from "./GenerationServicePage";

/** Where the page navigated to. */
function Location() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}

function cardPage(path: string, seed?: [readonly unknown[], unknown][]) {
  return renderPage(
    <>
      <GenerationServicePage />
      <Location />
    </>,
    { path, route: "/generation/:name", seed },
  );
}

const location = () => screen.getByTestId("location").textContent;
const targetButton = (label: string) => screen.getByRole("button", { name: new RegExp(`^${label}`) });

describe("the billing-api card on the in-memory mock", () => {
  it("shows the default target's coverage, its hint and every resource of the layout", async () => {
    cardPage("/generation/billing-api");

    expect(screen.getByText("Loading service…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();
    expect(screen.getByText("Generating Python SDK · layout is shared and read-only here")).toBeInTheDocument();
    expect(targetButton("Python SDK")).toHaveAttribute("aria-pressed", "true");
    expect(targetButton("Python SDK")).toHaveTextContent("0 / 4 merged");
    expect(targetButton("Ansible modules")).toHaveAttribute("aria-pressed", "false");
    expect(targetButton("Ansible modules")).toHaveTextContent("waits on Python SDK");
    expect(screen.getByText("Pull requests for this edition go to opentelekomcloud/python-t-cloud.")).toBeInTheDocument();

    // v1 and v2 both lay out an "invoices" resource
    expect(screen.getAllByText("invoices")).toHaveLength(2);
    expect(screen.getByText("payments")).toBeInTheDocument();
    expect(screen.getByText("misc")).toBeInTheDocument();
    expect(screen.getByText("4 endpoints · layout confirmed by valeriia")).toBeInTheDocument();
    expect(screen.getAllByText("3 endpoints · layout not confirmed yet")).toHaveLength(2);
    expect(screen.getByText("2 endpoints · layout not confirmed yet")).toBeInTheDocument();
  });

  it("opens the review of the resource waiting for it, and offers no Generate before the layout is confirmed", async () => {
    cardPage("/generation/billing-api");

    expect(await screen.findByRole("link", { name: "in review · PR 131" })).toHaveAttribute(
      "href",
      "/generation/billing-api/result/v1/v1_invoices",
    );
    // misc holds the endpoint not recognized in full, but confirming comes first
    expect(screen.getAllByText("confirm the layout first")).toHaveLength(3);
    for (const link of screen.getAllByRole("link", { name: "edit layout" })) {
      expect(link).toHaveAttribute("href", "/generation/billing-api/layout");
    }
    expect(screen.queryByText(/not recognized in full/)).toBeNull();
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
  });

  it("leads into the layout editor", async () => {
    cardPage("/generation/billing-api");

    expect(await screen.findByRole("link", { name: "Edit layout" })).toHaveAttribute(
      "href",
      "/generation/billing-api/layout",
    );
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
  });

  it("switches the target in the address", async () => {
    cardPage("/generation/billing-api");

    fireEvent.click(await screen.findByRole("button", { name: /^Ansible modules/ }));

    expect(location()).toBe("/generation/billing-api?target=ansible");
    expect(screen.getByText("Generating Ansible modules · layout is shared and read-only here")).toBeInTheDocument();
    expect(targetButton("Ansible modules")).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByText("Ansible modules is built on Python SDK — a resource opens up here once it is merged there."),
    ).toBeInTheDocument();

    fireEvent.click(targetButton("Python SDK"));

    expect(location()).toBe("/generation/billing-api");
  });

  it("opens on the target the address names, and keeps it on the way into the layout", async () => {
    cardPage("/generation/billing-api?target=ansible");

    expect(
      await screen.findByText("Generating Ansible modules · layout is shared and read-only here"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit layout" })).toHaveAttribute(
      "href",
      "/generation/billing-api/layout?target=ansible",
    );
    // invoices is confirmed but not merged in Python SDK yet
    expect(screen.getAllByText("waits on Python SDK")).toHaveLength(2);
  });

  it("names misc's endpoint not recognized in full once its layout is confirmed", async () => {
    const confirmed = generationResources("billing-api").map((r) =>
      r.name === "misc" ? { ...r, confirmedBy: "valeriia" } : r,
    );
    cardPage("/generation/billing-api", [[keys.genResources("billing-api"), confirmed]]);

    expect(await screen.findByText("1 endpoint not recognized in full")).toBeInTheDocument();
    expect(screen.getAllByText("confirm the layout first")).toHaveLength(2);
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
  });
});

describe("the way back to the list", () => {
  /** The list and the card under their own routes, so one can be left for the other. */
  function panel(path: string) {
    return renderPage(
      <>
        <Routes>
          <Route path="generation" element={<GenerationListPage />} />
          <Route path="generation/:name" element={<GenerationServicePage />} />
        </Routes>
        <Location />
      </>,
      { path, route: "*" },
    );
  }

  it("returns to the chip and the search the card was opened on, across a switch of target", async () => {
    panel("/generation?filter=failed");

    fireEvent.change(await screen.findByPlaceholderText("Filter services…"), { target: { value: "core" } });
    fireEvent.click(screen.getByText("customer-core"));

    expect(await screen.findByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation?filter=failed");

    fireEvent.click(targetButton("Ansible modules"));

    expect(location()).toBe("/generation/customer-core?target=ansible");
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation?filter=failed");

    fireEvent.click(screen.getByRole("link", { name: "All services" }));

    expect(location()).toBe("/generation?filter=failed");
    expect(await screen.findByRole("button", { name: "Failed 1" })).toHaveClass("bg-brand");
    // the search text is back in its field, and still narrows the list
    expect(screen.getByPlaceholderText("Filter services…")).toHaveValue("core");
    expect(screen.getByRole("button", { name: "All 1" })).toBeInTheDocument();
  });

  it("returns to the whole list when the card was opened on All", async () => {
    panel("/generation");

    fireEvent.click(await screen.findByTitle(/^Ansible modules · not connected · 0 of 4/));

    expect(await screen.findByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
  });
});

describe("other services on the mock", () => {
  it("says so when nothing is laid out", async () => {
    cardPage("/generation/device-mgmt");

    expect(await screen.findByText("Nothing laid out for this service yet.")).toBeInTheDocument();
    expect(targetButton("Python SDK")).toHaveTextContent("no resources");
  });

  it("fills the coverage bar with the merged share", async () => {
    cardPage("/generation/notifications-hub");

    const python = await screen.findByRole("button", { name: /^Python SDK/ });
    expect(python).toHaveTextContent("1 / 2 merged");
    expect(python.querySelector("[style]")).toHaveStyle({ width: "50%" });
    expect(screen.getByRole("link", { name: "merged · PR 118" })).toBeInTheDocument();
    expect(screen.getByText("3 endpoints · layout confirmed by valeriia")).toBeInTheDocument();
  });

  it("does not open a service that is not in Generation", async () => {
    cardPage("/generation/sms-gateway");

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
  });
});

describe("states the mock does not hold today", () => {
  const TARGETS: GenTarget[] = [
    { id: "python", label: "Python SDK", live: true, base: null, repo: "opentelekomcloud/python-t-cloud" },
    { id: "ansible", label: "Ansible modules", live: false, base: "python", repo: "opentelekomcloud/ansible-collection-cloud" },
    { id: "terraform", label: "Terraform provider", live: false, base: null, repo: "opentelekomcloud/terraform-provider" },
  ];
  const SERVICE: GenService = {
    name: "svc",
    targets: {
      python: { state: "failed", merged: 1, total: 8 },
      ansible: { state: "not_generated", merged: 0, total: 8 },
      terraform: { state: "not_generated", merged: 0, total: 8 },
    },
  };
  const res = (id: string, o: Partial<GenResource>): GenResource => ({
    id,
    version: "v1",
    name: id,
    endpoints: 2,
    notOk: 0,
    confirmedBy: "anna",
    jobs: {},
    ...o,
  });
  const RESOURCES: GenResource[] = [
    res("ready", {}),
    res("hollow", { endpoints: 0 }),
    res("unread", { endpoints: 3, notOk: 1 }),
    res("unconfirmed", { confirmedBy: null, notOk: 1 }),
    res("running", { jobs: { python: { status: "running", pr: null } } }),
    res("broken", { jobs: { python: { status: "failed", pr: null } } }),
    res("landed", { jobs: { python: { status: "merged", pr: 140 } } }),
  ];
  const SEED: [readonly unknown[], unknown][] = [
    [keys.genTargets, TARGETS],
    [keys.genServices, [SERVICE]],
    [keys.genResources("svc"), RESOURCES],
  ];

  it("offers Generate for a confirmed resource with every endpoint recognized, and says why for the rest", async () => {
    cardPage("/generation/svc", SEED);

    expect(await screen.findByRole("link", { name: "Generate" })).toHaveAttribute("href", "/generation/svc/spec/v1/ready");
    expect(screen.getByText("empty resource")).toBeInTheDocument();
    expect(screen.getByText("1 endpoint not recognized in full")).toBeInTheDocument();
    // one reason at a time: an unconfirmed layout is named before anything else
    expect(screen.getAllByText("confirm the layout first")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute("href", "/generation/svc/layout");
  });

  it("shows each job on the target, leading to its result", async () => {
    cardPage("/generation/svc", SEED);

    expect(await screen.findByRole("link", { name: "generating" })).toHaveAttribute(
      "href",
      "/generation/svc/result/v1/running",
    );
    expect(screen.getByRole("link", { name: "failed" })).toHaveAttribute("href", "/generation/svc/result/v1/broken");
    expect(screen.getByRole("link", { name: "merged · PR 140" })).toHaveAttribute(
      "href",
      "/generation/svc/result/v1/landed",
    );
  });

  it("holds a resource on a target that builds on another until it is merged there", async () => {
    cardPage("/generation/svc?target=ansible", SEED);

    // ready, running and broken are not merged on Python SDK; the coverage card says it too
    expect(await screen.findAllByText("waits on Python SDK")).toHaveLength(4);
    expect(screen.getByText("Ansible modules not connected yet")).toBeInTheDocument();
    expect(screen.getByText("2 endpoints · layout confirmed by anna · already merged in Python SDK")).toBeInTheDocument();
    // a reason of the resource itself comes before the base target
    expect(screen.getByText("1 endpoint not recognized in full")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
  });

  it("shows a target that is planned and builds on nothing", async () => {
    cardPage("/generation/svc?target=terraform", SEED);

    expect(await screen.findByText("Terraform provider is not connected yet — the layout is already shared with it.")).toBeInTheDocument();
    expect(targetButton("Terraform provider")).toHaveTextContent("planned");
    expect(screen.getAllByText("Terraform provider not connected yet")).toHaveLength(4);
  });

  it("says the service did not load, rather than showing it empty", async () => {
    cardPage("/generation/ghost", [
      [keys.genTargets, TARGETS],
      [keys.genServices, [{ ...SERVICE, name: "ghost" }]],
    ]);

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByText("Nothing laid out for this service yet.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
  });
});
