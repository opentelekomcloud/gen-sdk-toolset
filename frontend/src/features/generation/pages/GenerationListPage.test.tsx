import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { useLocation } from "react-router";
import { renderPage } from "../../../test/render";
import { keys } from "../../scan/api/queries";
import type { GenService, GenTarget } from "../data/types";
import { GenerationListPage } from "./GenerationListPage";

/** Where the page navigated to. */
function Location() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}

/** Route "*" keeps the page mounted after it navigates, so the address can be read. */
function listPage(path = "/generation", seed?: [readonly unknown[], unknown][]) {
  return renderPage(
    <>
      <GenerationListPage />
      <Location />
    </>,
    { path, route: "*", seed },
  );
}

const location = () => screen.getByTestId("location").textContent;

describe("the Generation list on the in-memory mock", () => {
  it("lists the services scanned in full or in part, with a column per target", async () => {
    listPage();

    expect(await screen.findByText("billing-api")).toBeInTheDocument();
    for (const name of ["customer-core", "device-mgmt", "notifications-hub", "tariff-catalog"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    // failed, still scanning, never scanned: not in Generation
    for (const name of ["sms-gateway", "legacy-soap-bridge", "payments-gw", "roaming-info"]) {
      expect(screen.queryByText(name)).toBeNull();
    }
    expect(screen.getByText("Python SDK")).toBeInTheDocument();
    expect(screen.getByText("Ansible modules · TBD")).toBeInTheDocument();
  });

  it("shows each service's state and merged share per target", async () => {
    listPage();

    expect(await screen.findByTitle("Python SDK · Waiting for review · 0 of 4 resources merged")).toHaveTextContent(
      "Waiting for review",
    );
    expect(screen.getByTitle("Python SDK · Failed · 1 of 3 resources merged")).toBeInTheDocument();
    expect(screen.getByTitle("Python SDK · Partial · 1 of 2 resources merged")).toBeInTheDocument();
    // Ansible is not connected and builds on Python
    expect(
      screen.getByTitle("Ansible modules · not connected · 0 of 4 resources merged · builds on Python SDK"),
    ).toHaveTextContent("not connected");
    expect(screen.getAllByText("1/3")).toHaveLength(1);
  });

  it("counts the services behind every chip", async () => {
    listPage();

    await screen.findByText("billing-api");
    for (const name of [
      "All 5",
      "Not generated 2",
      "In progress 0",
      "Failed 1",
      "Waiting for review 1",
      "Partial 1",
    ]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
  });
});

describe("the filter lives in the address", () => {
  it("opens narrowed to the services waiting for review", async () => {
    listPage("/generation?filter=review");

    expect(await screen.findByText("billing-api")).toBeInTheDocument();
    expect(screen.queryByText("customer-core")).toBeNull();
    expect(screen.queryByText("notifications-hub")).toBeNull();
  });

  it("opens narrowed to the services with nothing generated", async () => {
    listPage("/generation?filter=not_generated");

    expect(await screen.findByText("device-mgmt")).toBeInTheDocument();
    expect(screen.getByText("tariff-catalog")).toBeInTheDocument();
    for (const name of ["billing-api", "customer-core", "notifications-hub"]) {
      expect(screen.queryByText(name)).toBeNull();
    }
    expect(screen.getByRole("button", { name: "Not generated 2" })).toHaveClass("bg-brand");
    // device-mgmt has resources, none of them generated; tariff-catalog has none, so no merged share to show
    expect(screen.getByTitle("Python SDK · Not generated · 0 of 6 resources merged")).toBeInTheDocument();
    expect(screen.getByTitle("Python SDK · Not generated")).toBeInTheDocument();
    expect(screen.getAllByText(/^\d+\/\d+$/).map((e) => e.textContent)).toEqual(["0/6", "0/6"]);
  });

  it("opens narrowed to the services merged in part", async () => {
    listPage("/generation?filter=partial");

    expect(await screen.findByTitle("Python SDK · Partial · 1 of 2 resources merged")).toBeInTheDocument();
    expect(screen.getByText("notifications-hub")).toBeInTheDocument();
    expect(screen.getByText("1/2")).toBeInTheDocument();
    for (const name of ["billing-api", "customer-core", "device-mgmt", "tariff-catalog"]) {
      expect(screen.queryByText(name)).toBeNull();
    }
  });

  it("follows a chip click, and drops the filter again on All", async () => {
    listPage();

    fireEvent.click(await screen.findByRole("button", { name: "Failed 1" }));

    expect(location()).toBe("/generation?filter=failed");
    expect(screen.getByText("customer-core")).toBeInTheDocument();
    expect(screen.queryByText("billing-api")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "All 5" }));

    expect(location()).toBe("/generation");
    expect(screen.getByText("billing-api")).toBeInTheDocument();
  });

  it("says so when nothing matches", async () => {
    listPage("/generation?filter=in_progress");

    expect(await screen.findByText("No services match the current filter.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All 5" })).toBeInTheDocument();
    expect(screen.queryByText("billing-api")).toBeNull();
  });
});

describe("search", () => {
  it("narrows the rows and the chip counts together", async () => {
    listPage();

    fireEvent.change(await screen.findByPlaceholderText("Filter services…"), { target: { value: "core" } });

    expect(screen.getByText("customer-core")).toBeInTheDocument();
    expect(screen.queryByText("billing-api")).toBeNull();
    expect(screen.getByRole("button", { name: "All 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Failed 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Waiting for review 0" })).toBeInTheDocument();
  });
});

describe("the way into a service card", () => {
  it("opens on the default target from the row", async () => {
    listPage();

    fireEvent.click(await screen.findByText("billing-api"));

    expect(location()).toBe("/generation/billing-api");
  });

  it("opens on the clicked target from its cell", async () => {
    listPage();

    fireEvent.click(await screen.findByTitle(/^Ansible modules · not connected · 0 of 4/));

    expect(location()).toBe("/generation/billing-api?target=ansible");
  });
});

describe("states the mock does not hold today", () => {
  const TARGETS: GenTarget[] = [
    { id: "python", label: "Python SDK", live: true, base: null, repo: "opentelekomcloud/python-t-cloud" },
    { id: "ansible", label: "Ansible modules", live: false, base: "python", repo: "opentelekomcloud/ansible-collection-cloud" },
  ];
  const service = (name: string, state: GenService["targets"][string]["state"], merged: number): GenService => ({
    name,
    targets: {
      python: { state, merged, total: 2 },
      ansible: { state: "not_generated", merged: 0, total: 2 },
    },
  });
  const SEED: [readonly unknown[], unknown][] = [
    [keys.genTargets, TARGETS],
    [
      keys.genServices,
      [service("running-svc", "in_progress", 0), service("merged-svc", "done", 2)],
    ],
  ];

  it("shows a running generation as in progress", async () => {
    listPage("/generation", SEED);

    expect(await screen.findByTitle("Python SDK · In progress · 0 of 2 resources merged")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "In progress 1" })).toBeInTheDocument();
  });

  it("opens narrowed to the running generations, the pill spinning", async () => {
    listPage("/generation?filter=in_progress", SEED);

    const pill = await screen.findByTitle("Python SDK · In progress · 0 of 2 resources merged");
    expect(pill.querySelector(".animate-spin")).not.toBeNull();
    expect(screen.getByText("running-svc")).toBeInTheDocument();
    expect(screen.queryByText("No services match the current filter.")).toBeNull();
  });

  it("leaves out a service merged in full, from the rows and the counts", async () => {
    listPage("/generation", SEED);

    expect(await screen.findByText("running-svc")).toBeInTheDocument();
    expect(screen.queryByText("merged-svc")).toBeNull();
    expect(screen.getByRole("button", { name: "All 1" })).toBeInTheDocument();
  });
});
