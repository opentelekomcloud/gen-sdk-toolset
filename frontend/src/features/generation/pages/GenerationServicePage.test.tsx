import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes, useLocation, useNavigate } from "react-router";
import { backend, CONFLICT, FAILED, FORBIDDEN, later, NOT_FOUND, pollAgain, refresh, renderPage } from "../../../test/render";
import { mockFails } from "../../../test/mockFails";
import { endpoint, generationList, layout, listedSeed } from "../../../test/fixtures";
import { expectRetryJoinsResources, mockSeeds } from "../../../test/generationMock";
import { tokenWithRoles } from "../../../test/token";
import { keys } from "../../scan/api/queries";
import { generationResources } from "../data/mock";
import type { GenEndpoint, GenJob, GenJobStatus, GenResource, GenTarget } from "../data/types";
import { GenerationLayoutPage } from "./GenerationLayoutPage";
import { GenerationListPage } from "./GenerationListPage";
import { GenerationServicePage } from "./GenerationServicePage";

/* Every service of the mock with endpoints is in the server's list, with a stored layout. */
const MOCK = mockSeeds();

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
    { path, route: "/generation/:name", seed: [...MOCK, ...(seed ?? [])] },
  );
}

const location = () => screen.getByTestId("location").textContent;

/* The way back carries the filter chip, and the card shows its targets and jobs, each behind its flag;
   the job tags lead to the result only while that page is switched on. The tests drive all three on
   unless they say otherwise. */
const flags = vi.hoisted(() => ({ showGenState: true, showGenResult: true, showGenJobs: true }));
vi.mock("../flags", () => ({
  /* the layout editor as it ships: no origin badge */
  SHOW_LAYOUT_ORIGIN: false,
  get SHOW_GEN_STATE() {
    return flags.showGenState;
  },
  get SHOW_GEN_RESULT() {
    return flags.showGenResult;
  },
  get SHOW_GEN_JOBS() {
    return flags.showGenJobs;
  },
}));

/* The layout page, reached from the card, reads the signed-in user. */
vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: tokenWithRoles("viewer"), profile: { preferred_username: "ada@otc.test" } },
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

afterEach(() => {
  flags.showGenState = true;
  flags.showGenResult = true;
  flags.showGenJobs = true;
  vi.unstubAllGlobals();
});

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

  it("holds every resource on Ansible modules until Python SDK merges it, and shows none of Python's jobs", async () => {
    cardPage("/generation/billing-api?target=ansible");

    const ansible = await screen.findByRole("button", { name: /^Ansible modules/ });
    expect(ansible).toHaveAttribute("aria-pressed", "true");
    expect(ansible.querySelector("[style]")).toHaveStyle({ width: "0%" });
    expect(targetButton("Python SDK")).toHaveAttribute("aria-pressed", "false");
    expect(targetButton("Python SDK")).toHaveTextContent("0 / 4 merged");
    expect(
      screen.getByText("Ansible modules is built on Python SDK — a resource opens up here once it is merged there."),
    ).toBeInTheDocument();
    // the coverage card and the table's column
    expect(screen.getAllByText("Ansible modules")).toHaveLength(2);

    // invoices is in review on Python SDK: that job is not Ansible's, and it is not merged anywhere
    expect(screen.getByText("4 endpoints · layout confirmed by valeriia")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /in review/ })).toBeNull();
    // the unconfirmed layout is named before the base target, with the way into the layout on this target
    expect(screen.getAllByText("confirm the layout first")).toHaveLength(3);
    const fixes = screen.getAllByRole("link", { name: "edit layout" });
    expect(fixes).toHaveLength(3);
    for (const link of fixes) expect(link).toHaveAttribute("href", "/generation/billing-api/layout?target=ansible");
    // waiting on Python SDK comes before Ansible not being connected
    expect(screen.queryByText("Ansible modules not connected yet")).toBeNull();
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
  });

  it("names misc's endpoint not recognized in full once its layout is confirmed", async () => {
    const confirmed = generationResources("billing-api").map((r) =>
      r.name === "misc" ? { ...r, confirmedBy: "valeriia", confirmedAt: "2026-08-12T09:24:00Z" } : r,
    );
    cardPage("/generation/billing-api", [[keys.genResources("billing-api"), confirmed]]);

    expect(await screen.findByText("1 endpoint not recognized in full")).toBeInTheDocument();
    expect(screen.getAllByText("confirm the layout first")).toHaveLength(2);
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
  });
});

describe("the customer-core card on the in-memory mock", () => {
  it("shows the merged resource, the failed one and the new one on Python SDK", async () => {
    cardPage("/generation/customer-core");

    expect(await screen.findByRole("heading", { name: "customer-core" })).toBeInTheDocument();
    const python = targetButton("Python SDK");
    expect(python).toHaveAttribute("aria-pressed", "true");
    expect(python).toHaveTextContent("1 / 3 merged");
    expect(python.querySelector("[style]")).toHaveStyle({ width: "33%" });
    expect(targetButton("Ansible modules")).toHaveTextContent("waits on Python SDK");
    expect(screen.getByText("Pull requests for this edition go to opentelekomcloud/python-t-cloud.")).toBeInTheDocument();

    expect(screen.getByText("customers")).toBeInTheDocument();
    expect(screen.getByText("contacts")).toBeInTheDocument();
    expect(screen.getByText("addresses")).toBeInTheDocument();
    expect(screen.getByText("4 endpoints · layout confirmed by ivan")).toBeInTheDocument();
    // ivan confirmed contacts before generating it (owner decision)
    expect(screen.getByText("2 endpoints · layout confirmed by ivan")).toBeInTheDocument();
    expect(screen.getByText("2 endpoints · layout not confirmed yet")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "merged · PR 122" })).toHaveAttribute(
      "href",
      "/generation/customer-core/result/v1/c_customers",
    );
    // the failed job opened no pull request; it leads to its result, where it can be looked into
    expect(screen.getByRole("link", { name: "failed" })).toHaveAttribute(
      "href",
      "/generation/customer-core/result/v1/c_contacts",
    );
    // only addresses is held
    expect(screen.getAllByText("confirm the layout first")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute("href", "/generation/customer-core/layout");
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
  });

  it("opens the merged resource up on Ansible modules, which is not connected yet", async () => {
    cardPage("/generation/customer-core?target=ansible");

    expect(
      await screen.findByText("4 endpoints · layout confirmed by ivan · already merged in Python SDK"),
    ).toBeInTheDocument();
    expect(screen.getByText("Ansible modules not connected yet")).toBeInTheDocument();
    // the coverage card waits on the base target whatever is merged there
    expect(targetButton("Ansible modules")).toHaveTextContent("waits on Python SDK");
    expect(targetButton("Python SDK")).toHaveTextContent("1 / 3 merged");
    // Python's jobs are not Ansible's: contacts, confirmed, waits on its merge there like the coverage card
    expect(screen.queryByRole("link", { name: /merged|failed/ })).toBeNull();
    expect(screen.getAllByText("waits on Python SDK")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute(
      "href",
      "/generation/customer-core/layout?target=ansible",
    );
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
  });
});

describe("the notifications-hub card on the in-memory mock", () => {
  it("shows one resource merged on Python SDK and the other held, filling the coverage bar with the merged share", async () => {
    cardPage("/generation/notifications-hub");

    expect(await screen.findByRole("heading", { name: "notifications-hub" })).toBeInTheDocument();
    const python = targetButton("Python SDK");
    expect(python).toHaveAttribute("aria-pressed", "true");
    expect(python).toHaveTextContent("1 / 2 merged");
    expect(python.querySelector("[style]")).toHaveStyle({ width: "50%" });
    const ansible = targetButton("Ansible modules");
    expect(ansible).toHaveTextContent("waits on Python SDK");
    expect(ansible.querySelector("[style]")).toHaveStyle({ width: "0%" });
    expect(screen.getByText("Pull requests for this edition go to opentelekomcloud/python-t-cloud.")).toBeInTheDocument();

    expect(screen.getByText("topics")).toBeInTheDocument();
    expect(screen.getByText("3 endpoints · layout confirmed by valeriia")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "merged · PR 118" })).toHaveAttribute(
      "href",
      "/generation/notifications-hub/result/v1/n_topics",
    );

    expect(screen.getByText("subscriptions")).toBeInTheDocument();
    expect(screen.getByText("2 endpoints · layout not confirmed yet")).toBeInTheDocument();
    expect(screen.getByText("confirm the layout first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute(
      "href",
      "/generation/notifications-hub/layout",
    );
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
  });

  it("offers Generate for subscriptions once its layout is confirmed", async () => {
    const confirmed = generationResources("notifications-hub").map((r) =>
      r.name === "subscriptions" ? { ...r, confirmedBy: "valeriia", confirmedAt: "2026-08-12T09:24:00Z" } : r,
    );
    cardPage("/generation/notifications-hub", [[keys.genResources("notifications-hub"), confirmed]]);

    expect(await screen.findByRole("link", { name: "Generate" })).toHaveAttribute(
      "href",
      "/generation/notifications-hub/spec/v1/n_subscriptions",
    );
    expect(screen.getByRole("link", { name: "merged · PR 118" })).toBeInTheDocument();
    expect(screen.queryByText("confirm the layout first")).toBeNull();
  });

  it("opens the merged resource up on Ansible modules, which is not connected yet", async () => {
    cardPage("/generation/notifications-hub?target=ansible");

    expect(
      await screen.findByText("3 endpoints · layout confirmed by valeriia · already merged in Python SDK"),
    ).toBeInTheDocument();
    expect(screen.getByText("Ansible modules not connected yet")).toBeInTheDocument();
    expect(targetButton("Ansible modules")).toHaveAttribute("aria-pressed", "true");
    expect(targetButton("Python SDK")).toHaveTextContent("1 / 2 merged");
    expect(
      screen.getByText("Ansible modules is built on Python SDK — a resource opens up here once it is merged there."),
    ).toBeInTheDocument();
    // only the coverage card waits on the base target: no resource here does
    expect(screen.getAllByText("waits on Python SDK")).toHaveLength(1);
    // Python's merged job is not Ansible's
    expect(screen.queryByRole("link", { name: /merged/ })).toBeNull();
    expect(screen.getByText("2 endpoints · layout not confirmed yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "edit layout" })).toHaveAttribute(
      "href",
      "/generation/notifications-hub/layout?target=ansible",
    );
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
      { path, route: "*", seed: MOCK },
    );
  }

  it("returns to the chip and the search the card was opened on, across a switch of target", async () => {
    panel("/generation?filter=failed");

    fireEvent.change(await screen.findByPlaceholderText("Filter services…"), { target: { value: "core" } });
    await waitFor(() => expect(location()).toBe("/generation?filter=failed&q=core"));
    fireEvent.click(screen.getByText("customer-core"));

    const back = "/generation?filter=failed&q=core";
    expect(await screen.findByRole("link", { name: "All services" })).toHaveAttribute("href", back);

    fireEvent.click(targetButton("Ansible modules"));

    expect(location()).toBe("/generation/customer-core?target=ansible");
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", back);

    fireEvent.click(screen.getByRole("link", { name: "All services" }));

    expect(location()).toBe(back);
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
  it("does not open a service without endpoints, which the server never lists (ADR-0087)", async () => {
    cardPage("/generation/tariff-catalog");

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "tariff-catalog" })).toBeNull();
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
  /** `n` endpoints, the last `notOk` of them with a document not recognized in full. */
  const eps = (id: string, n: number, notOk = 0): GenEndpoint[] =>
    Array.from({ length: n }, (_, i) => ({
      id: `${id}-${i}`,
      method: "GET",
      uri: `/v1/${id}/${i}`,
      title: `${id} ${i}`,
      src: `https://github.com/opentelekomcloud-docs/svc/blob/mockcommit/api-ref/source/${id}-${i}.rst`,
      status: i >= n - notOk ? "partial" : "ok",
    }));
  const res = (id: string, o: Partial<GenResource>): GenResource => ({
    id,
    version: "v1",
    name: id,
    endpoints: eps(id, 2),
    origin: "auto",
    confirmedBy: "anna",
    confirmedAt: "2026-08-01T10:00:00Z",
    jobs: {},
    ...o,
  });
  const job = (status: GenJobStatus, pr: number | null): GenJob => ({
    id: 3000,
    status,
    pr,
    startedBy: "anna",
    startedAt: "2026-08-02T10:00:00Z",
    mergedBy: status === "merged" ? "ivan" : null,
    mergedAt: status === "merged" ? "2026-08-03T10:00:00Z" : null,
    error: null,
  });
  const RESOURCES: GenResource[] = [
    res("ready", {}),
    res("hollow", { endpoints: [] }),
    res("unread", { endpoints: eps("unread", 3, 1) }),
    res("unconfirmed", { confirmedBy: null, confirmedAt: null, endpoints: eps("unconfirmed", 2, 1) }),
    res("running", { jobs: { python: job("running", null) } }),
    res("broken", { jobs: { python: job("failed", null) } }),
    res("landed", { jobs: { python: job("merged", 140) } }),
  ];
  const SEED: [readonly unknown[], unknown][] = [
    [keys.genTargets, TARGETS],
    listedSeed("svc"),
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

  it("fills the coverage of each target from the resources merged there", async () => {
    cardPage("/generation/svc", SEED);

    expect(await screen.findByRole("heading", { name: "svc" })).toBeInTheDocument();
    expect(targetButton("Python SDK")).toHaveTextContent("1 / 7 merged");
  });

  it("says the service did not load, rather than showing it empty", async () => {
    mockFails.resources = true;
    cardPage("/generation/ghost", [
      [keys.genTargets, TARGETS],
      listedSeed("ghost"),
    ]);

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByText("Nothing laid out for this service yet.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
  });

  it("joins a refresh of the resources already asking when Retry is clicked (ADR-0081, ADR-0084)", async () => {
    const { client } = cardPage("/generation/billing-api");
    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();
    await expectRetryJoinsResources(client, "billing-api");
  });
});

/** A service the grouping has not run for yet. */
const ECS = "opentelekomcloud-docs/ecs";
const NO_LAYOUT = layout({ has_layout: false, versions: [], no_version: [] });

describe("the services the card opens for (ADR-0086)", () => {
  const LIST = "/api/generation/services";
  const LAYOUT = "/api/generation/services/billing-api/layout";

  /* The card as it ships: generation itself switched off (ISS-0038). */
  beforeEach(() => {
    flags.showGenJobs = false;
  });

  it("opens for a service of the server's list with its title and the way to its layout", async () => {
    cardPage("/generation/opentelekomcloud-docs%2Fecs", [listedSeed(ECS), [keys.genLayout(ECS), NO_LAYOUT]]);

    expect(await screen.findByRole("heading", { name: "opentelekomcloud-docs/ecs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
    // the layout of the same service, the repo one segment of the address (ADR-0063)
    expect(screen.getByRole("link", { name: "Edit layout" })).toHaveAttribute(
      "href",
      "/generation/opentelekomcloud-docs%2Fecs/layout",
    );
    // no coverage: the server has no generation data yet
    expect(screen.queryByText(/^Generating /)).toBeNull();
  });

  it("is reached by a click in the list, and leads on to the layout of the same service", async () => {
    // the list as it ships, on the server's rows
    flags.showGenState = false;
    renderPage(
      <>
        <Routes>
          <Route path="generation" element={<GenerationListPage />} />
          <Route path="generation/:name" element={<GenerationServicePage />} />
          <Route path="generation/:name/layout" element={<GenerationLayoutPage />} />
        </Routes>
        <Location />
      </>,
      {
        path: "/generation",
        route: "*",
        seed: [listedSeed(ECS), [keys.genLayout(ECS), NO_LAYOUT]],
      },
    );

    fireEvent.click(await screen.findByText(ECS));

    expect(await screen.findByRole("heading", { name: ECS })).toBeInTheDocument();
    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs");

    fireEvent.click(screen.getByRole("link", { name: "Edit layout" }));

    expect(await screen.findByText("No layout yet. Its resources appear here once the service is grouped.")).toBeInTheDocument();
    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs/layout");
  });

  it("carries the target the address names into the layout", async () => {
    cardPage("/generation/opentelekomcloud-docs%2Fecs?target=ansible", [listedSeed(ECS), [keys.genLayout(ECS), NO_LAYOUT]]);

    expect(await screen.findByRole("link", { name: "Edit layout" })).toHaveAttribute(
      "href",
      "/generation/opentelekomcloud-docs%2Fecs/layout?target=ansible",
    );
  });

  it("reads nothing of the mock for a service it holds: no job, no Generate", async () => {
    // a layout the mock cannot give would fail the card if it were still read
    mockFails.resources = true;
    cardPage("/generation/billing-api");

    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();
    // the stored layout holds no resource; the mock's billing-api would have them
    expect(screen.getByText("Nothing laid out for this service yet.")).toBeInTheDocument();
    expect(screen.queryByText("Failed to load service")).toBeNull();
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
    expect(screen.queryByText("in review · PR 131")).toBeNull();
  });

  it("does not open a service of the mock that the server's list does not hold", async () => {
    cardPage("/generation/billing-api", [listedSeed("customer-core")]);

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "billing-api" })).toBeNull();
  });

  it("checks against the whole list, not one a search on the list page narrowed", async () => {
    const requested: string[] = [];
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      requested.push(String(input));
      return new Response(JSON.stringify(generationList("customer-core")));
    });
    // the list page searched "bill" and holds billing-api; the whole list does not
    renderPage(<GenerationServicePage />, {
      path: "/generation/billing-api",
      route: "/generation/:name",
      seed: [[keys.genList({ q: "bill" }), generationList("billing-api")]],
    });

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(requested).toContain(LIST);
    expect(requested.filter((url) => url.startsWith(`${LIST}?`))).toEqual([]);
  });

  it("joins a refresh already asking when Retry is clicked, rather than asking a second time", async () => {
    const answers: Record<string, unknown> = { [LIST]: generationList("billing-api"), [LAYOUT]: layout() };
    const api = backend(answers);
    const { client } = renderPage(<GenerationServicePage />, { path: "/generation/billing-api", route: "/generation/:name" });
    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();
    // a refresh fails over the list already shown: TanStack keeps that answer, which a cancelling refetch would act on
    answers[LIST] = FAILED;
    await refresh(client, keys.genList());
    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();

    const pending = later();
    answers[LIST] = pending.arrived;
    await act(async () => {
      void client.refetchQueries({ queryKey: keys.genList() });
    });
    expect(api.calls(LIST)).toBe(3);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    pending.send(generationList("billing-api"));

    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();
    expect(api.calls(LIST)).toBe(3);
  });

  it("turns into the page a direct address shows once a refresh no longer lists the service", async () => {
    const answers: Record<string, unknown> = { [LIST]: generationList("billing-api"), [LAYOUT]: layout() };
    backend(answers);
    const { client } = renderPage(<GenerationServicePage />, { path: "/generation/billing-api", route: "/generation/:name" });
    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();

    // excluded by someone else, or out of the list since its active snapshot changed
    answers[LIST] = generationList("customer-core");
    await refresh(client, keys.genList());

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All services" })).toHaveAttribute("href", "/generation");
  });

  it("shows a failed refresh of the list as a failure with Retry, not as Page not found", async () => {
    const answers: Record<string, unknown> = { [LIST]: generationList("billing-api"), [LAYOUT]: layout() };
    backend(answers);
    const { client } = renderPage(<GenerationServicePage />, { path: "/generation/billing-api", route: "/generation/:name" });
    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();

    answers[LIST] = FAILED;
    await refresh(client, keys.genList());

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByText("Page not found.")).toBeNull();
    // the answer before the failure is not shown as current either
    expect(screen.queryByRole("heading", { name: "billing-api" })).toBeNull();

    answers[LIST] = generationList("billing-api");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "billing-api" })).toBeInTheDocument();
  });

  it("shows a first load of the list that failed as a failure with Retry, not as Page not found", async () => {
    backend({ [LIST]: FAILED });
    renderPage(<GenerationServicePage />, { path: "/generation/billing-api", route: "/generation/:name" });

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByText("Page not found.")).toBeNull();
  });
});

describe("the resources of a stored layout on the card (ISS-0040)", () => {
  const LIST = "/api/generation/services";
  const LAYOUT = "/api/generation/services/billing-api/layout";
  const PATH = "/generation/billing-api";

  /* The card as it ships: generation itself switched off. */
  beforeEach(() => {
    flags.showGenJobs = false;
  });

  const unconfirmed = { confirmed_by: null, confirmed_at: null };
  const confirmedBy = (by: string) => ({ confirmed_by: by, confirmed_at: "2026-11-02T10:00:00Z" });
  const resource = (id: number, name: string, confirmation: object, endpoints = [endpoint({ id })]) => ({
    id,
    name,
    endpoints,
    ...unconfirmed,
    ...confirmation,
  });

  /** Two versions with resources, one with only an endpoint left unassigned, and one without a version. */
  const laidOut = (first: object = unconfirmed) =>
    layout({
      versions: [
        {
          api_version: "v1",
          resources: [resource(1, "invoices", first), resource(2, "payments", unconfirmed)],
          unassigned: [endpoint({ id: 10 })],
        },
        { api_version: "v2", resources: [resource(3, "refunds", unconfirmed)], unassigned: [] },
        { api_version: "v3", resources: [], unassigned: [endpoint({ id: 11 })] },
      ],
      no_version: [endpoint({ id: 12 })],
    });

  function card(answers: Record<string, unknown>) {
    answers[LIST] ??= generationList("billing-api");
    backend(answers);
    return renderPage(<GenerationServicePage />, { path: PATH, route: "/generation/:name" });
  }

  const centre = () => screen.getByRole("region", { name: "Resources" });

  it("sums the layout up while no resource is confirmed, counting no endpoint left out of a resource (ADR-0062)", async () => {
    card({ [LAYOUT]: laidOut() });

    // v3 and the endpoints left out of a resource are not counted
    expect(await screen.findByText("3 resources in 2 versions, confirmation needed")).toBeInTheDocument();
    expect(within(centre()).getByRole("link", { name: "Edit layout" })).toHaveAttribute("href", "/generation/billing-api/layout");
    expect(within(centre()).queryByRole("group", { name: "invoices" })).toBeNull();
    expect(screen.queryByText("confirm the layout first")).toBeNull();
  });

  it("says one resource in one version in the singular", async () => {
    card({
      [LAYOUT]: layout({
        versions: [{ api_version: "v1", resources: [resource(1, "invoices", unconfirmed)], unassigned: [] }],
      }),
    });

    expect(await screen.findByText("1 resource in 1 version, confirmation needed")).toBeInTheDocument();
  });

  it("leads into the editor from a layout that holds no resource at all", async () => {
    card({ [LAYOUT]: layout({ versions: [{ api_version: "v1", resources: [], unassigned: [endpoint()] }] }) });

    expect(await screen.findByText("Nothing laid out for this service yet.")).toBeInTheDocument();
    expect(within(centre()).getByRole("link", { name: "Edit layout" })).toHaveAttribute("href", "/generation/billing-api/layout");
    expect(screen.queryByText(/confirmation needed/)).toBeNull();
  });

  it("keeps the target the address names on the way into the editor", async () => {
    backend({ [LIST]: generationList("billing-api"), [LAYOUT]: laidOut() });
    renderPage(<GenerationServicePage />, { path: `${PATH}?target=ansible`, route: "/generation/:name" });

    expect(await screen.findByText(/confirmation needed/)).toBeInTheDocument();
    expect(within(centre()).getByRole("link", { name: "Edit layout" })).toHaveAttribute(
      "href",
      "/generation/billing-api/layout?target=ansible",
    );
  });

  it("shows every resource once one is confirmed, each with its version, endpoints and confirmation", async () => {
    card({ [LAYOUT]: laidOut(confirmedBy("ada@otc.test")) });

    const invoices = await screen.findByRole("group", { name: "invoices" });
    expect(within(invoices).getByText("v1 · 1 endpoint · layout confirmed by ada@otc.test")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "payments" })).getByText("v1 · 1 endpoint · layout not confirmed yet")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "refunds" })).getByText("v2 · 1 endpoint · layout not confirmed yet")).toBeInTheDocument();
    expect(screen.queryByText(/confirmation needed/)).toBeNull();
  });

  it("says why each row is held back by its layout, and offers no Generate and no job", async () => {
    card({
      [LAYOUT]: layout({
        versions: [
          {
            api_version: "v1",
            resources: [
              resource(1, "invoices", confirmedBy("ada@otc.test")),
              resource(2, "payments", unconfirmed),
              resource(3, "refunds", confirmedBy("ada@otc.test"), []),
              resource(4, "credits", confirmedBy("ada@otc.test"), [
                endpoint({ id: 4 }),
                endpoint({ id: 5, overall_status: "partial" }),
                endpoint({ id: 6, overall_status: "failed" }),
              ]),
            ],
            unassigned: [],
          },
        ],
      }),
    });

    const row = async (name: string) => screen.findByRole("group", { name });
    // nothing holds it
    expect(within(await row("invoices")).queryByText(/first|empty|not recognized/)).toBeNull();
    const payments = await row("payments");
    expect(within(payments).getByText("confirm the layout first")).toBeInTheDocument();
    expect(within(payments).getByRole("link", { name: "edit layout" })).toHaveAttribute("href", "/generation/billing-api/layout");
    expect(within(await row("refunds")).getByText("empty resource")).toBeInTheDocument();
    expect(within(await row("credits")).getByText("2 endpoints not recognized in full")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
    expect(screen.queryByText(/in review|merged|running/)).toBeNull();
  });

  /** One resource for each reason its layout holds it back by, and one it does not hold back. */
  const everyReason = () =>
    layout({
      versions: [
        {
          api_version: "v1",
          resources: [
            resource(1, "invoices", confirmedBy("ada@otc.test")),
            resource(2, "payments", unconfirmed),
            resource(3, "refunds", confirmedBy("ada@otc.test"), []),
            resource(4, "credits", confirmedBy("ada@otc.test"), [endpoint({ id: 4, overall_status: "partial" })]),
          ],
          unassigned: [],
        },
      ],
    });

  it("says Ansible modules is not connected yet on a row its layout does not hold back (ADR-0055)", async () => {
    backend({ [LIST]: generationList("billing-api"), [LAYOUT]: everyReason() });
    renderPage(<GenerationServicePage />, { path: `${PATH}?target=ansible`, route: "/generation/:name" });

    const row = async (name: string) => screen.findByRole("group", { name });
    expect(within(await row("invoices")).getByText("Ansible modules not connected yet")).toBeInTheDocument();
    // the layout's reason comes first, and is the only one said
    expect(within(await row("payments")).getByText("confirm the layout first")).toBeInTheDocument();
    expect(within(await row("refunds")).getByText("empty resource")).toBeInTheDocument();
    expect(within(await row("credits")).getByText("1 endpoint not recognized in full")).toBeInTheDocument();
    expect(screen.getAllByText("Ansible modules not connected yet")).toHaveLength(1);
    expect(screen.queryByRole("link", { name: "Generate" })).toBeNull();
  });

  it("says so as soon as Ansible modules is chosen, and no more once Python SDK is again", async () => {
    card({ [LAYOUT]: everyReason() });

    const invoices = await screen.findByRole("group", { name: "invoices" });
    expect(within(invoices).queryByText(/not connected/)).toBeNull();

    fireEvent.click(targetButton("Ansible modules"));
    expect(within(screen.getByRole("group", { name: "invoices" })).getByText("Ansible modules not connected yet")).toBeInTheDocument();

    fireEvent.click(targetButton("Python SDK"));
    expect(within(screen.getByRole("group", { name: "invoices" })).queryByText(/not connected/)).toBeNull();
  });

  it("brings the summary back once a refresh finds no confirmed resource left, and the table once one is again", async () => {
    const answers: Record<string, unknown> = { [LAYOUT]: laidOut(confirmedBy("ada@otc.test")) };
    const { client } = card(answers);
    expect(await screen.findByRole("group", { name: "invoices" })).toBeInTheDocument();

    // an edit took the confirmation back (ADR-0066)
    answers[LAYOUT] = laidOut();
    await pollAgain(client, keys.genLayout("billing-api"));

    expect(await screen.findByText("3 resources in 2 versions, confirmation needed")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "invoices" })).toBeNull();

    answers[LAYOUT] = laidOut(confirmedBy("ada@otc.test"));
    await pollAgain(client, keys.genLayout("billing-api"));

    expect(await screen.findByRole("group", { name: "invoices" })).toBeInTheDocument();
  });
});

describe("with the result page switched off (ADR-0086)", () => {
  it("shows each job as a tag that leads nowhere, as its result is not found", async () => {
    flags.showGenResult = false;
    cardPage("/generation/billing-api");

    expect(await screen.findByText("in review · PR 131")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "in review · PR 131" })).toBeNull();
  });
});

describe("the preliminary grouping of a service without a layout (ISS-0039)", () => {
  const LIST = "/api/generation/services";
  const LAYOUT = "/api/generation/services/opentelekomcloud-docs%2Fecs/layout";
  const PATH = "/generation/opentelekomcloud-docs%2Fecs";

  /* The card as it ships: generation itself switched off. */
  beforeEach(() => {
    flags.showGenJobs = false;
  });

  /** The card of ecs on a backend that answers `answers`, starting without a layout. */
  async function ecsCard(answers: Record<string, unknown>) {
    const api = backend(answers);
    const { client } = renderPage(<GenerationServicePage />, { path: PATH, route: "/generation/:name" });
    expect(await screen.findByRole("button", { name: "Generate layout" })).toBeInTheDocument();
    return { ...api, client };
  }

  it("files the answer under the service it was started for, when the page moves on to another meanwhile", async () => {
    const OTHER = "opentelekomcloud-docs/evs";
    const OTHER_LAYOUT = "/api/generation/services/opentelekomcloud-docs%2Fevs/layout";
    /** The same page, reused for another service, as the router does for a new address of its route. */
    function MoveOn() {
      const navigate = useNavigate();
      return (
        <button type="button" onClick={() => navigate("/generation/opentelekomcloud-docs%2Fevs")}>
          move on
        </button>
      );
    }
    const answers: Record<string, unknown> = {
      [LIST]: generationList(ECS, OTHER),
      [LAYOUT]: NO_LAYOUT,
      [OTHER_LAYOUT]: NO_LAYOUT,
    };
    backend(answers);
    const { client } = renderPage(
      <>
        <GenerationServicePage />
        <MoveOn />
      </>,
      { path: PATH, route: "/generation/:name" },
    );
    const generate = await screen.findByRole("button", { name: "Generate layout" });
    const start = later();
    answers[LAYOUT] = start.arrived;
    fireEvent.click(generate);
    expect(await screen.findByText("Grouping endpoints…")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "move on" }));

    // the other service has its own button, not the spinner of a start that is not its own
    expect(await screen.findByRole("heading", { name: OTHER })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate layout" })).toBeInTheDocument();
    expect(screen.queryByText("Grouping endpoints…")).toBeNull();

    await act(async () => {
      start.send(layout());
      await start.arrived;
    });

    await waitFor(() => expect(client.getQueryData<{ has_layout: boolean }>(keys.genLayout(ECS))?.has_layout).toBe(true));
    expect(client.getQueryData<{ has_layout: boolean }>(keys.genLayout(OTHER))?.has_layout).toBe(false);
    expect(screen.getByRole("button", { name: "Generate layout" })).toBeInTheDocument();
  });

  it("shows only Generate layout in the centre (ADR-0056)", async () => {
    await ecsCard({ [LIST]: generationList(ECS), [LAYOUT]: NO_LAYOUT });

    // the button is all the centre holds
    expect(screen.getByRole("region", { name: "Resources" })).toHaveTextContent(/^Generate layout$/);
  });

  it("starts the grouping, spins while it runs, and shows the stored layout from its answer", async () => {
    const answers: Record<string, unknown> = { [LIST]: generationList(ECS), [LAYOUT]: NO_LAYOUT };
    const api = await ecsCard(answers);
    // something the layout feeds, as a page left open would hold it
    api.client.setQueryData(keys.genResources(ECS), []);
    const start = later();
    answers[LAYOUT] = start.arrived;

    fireEvent.click(screen.getByRole("button", { name: "Generate layout" }));

    // a spinner in place of the button while the server groups (ADR-0060)
    expect(await screen.findByText("Grouping endpoints…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate layout" })).toBeNull();

    start.send(layout());

    expect(await screen.findByText("1 resource in 1 version, confirmation needed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate layout" })).toBeNull();
    // the read and the start: the answer is shown as it is, not read again
    expect(api.calls(LAYOUT)).toBe(2);
    // what the layout feeds is read again, as after any change of the layout
    expect(api.client.getQueryState(keys.genResources(ECS))?.isInvalidated).toBe(true);
  });

  it("keeps the started layout over an older read of it still under way", async () => {
    const answers: Record<string, unknown> = { [LIST]: generationList(ECS), [LAYOUT]: NO_LAYOUT };
    const api = await ecsCard(answers);
    const poll = later();
    let asked = 0;
    // the periodic read goes out first and answers late; the start answers at once
    answers[LAYOUT] = () => (asked++ === 0 ? poll.arrived : layout());
    await pollAgain(api.client, keys.genLayout(ECS));

    fireEvent.click(screen.getByRole("button", { name: "Generate layout" }));
    expect(await screen.findByText("1 resource in 1 version, confirmation needed")).toBeInTheDocument();

    // the read from before the grouping was dropped: nothing is left under way that could land on top
    expect(api.client.getQueryState(keys.genLayout(ECS))?.fetchStatus).toBe("idle");
    expect(api.client.getQueryData<{ has_layout: boolean }>(keys.genLayout(ECS))?.has_layout).toBe(true);

    await act(async () => {
      poll.send(NO_LAYOUT);
      await poll.arrived;
    });
    expect(screen.queryByRole("button", { name: "Generate layout" })).toBeNull();
  });

  it("shows a failed grouping with Retry in place of the button, and Retry starts it again (ADR-0061)", async () => {
    const answers: Record<string, unknown> = { [LIST]: generationList(ECS), [LAYOUT]: NO_LAYOUT };
    await ecsCard(answers);
    answers[LAYOUT] = FAILED;

    fireEvent.click(screen.getByRole("button", { name: "Generate layout" }));

    const failure = await screen.findByRole("alert");
    expect(failure).toHaveTextContent("Failed to group endpoints");
    expect(failure).not.toHaveTextContent("your role does not allow that");
    expect(screen.queryByRole("button", { name: "Generate layout" })).toBeNull();

    const again = later();
    answers[LAYOUT] = again.arrived;
    fireEvent.click(within(failure).getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Grouping endpoints…")).toBeInTheDocument();
    again.send(layout());
    expect(await screen.findByText("1 resource in 1 version, confirmation needed")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says why a refused start was refused: the role, not a failed grouping", async () => {
    // the session of this suite is a viewer's; until ISS-0044 hides the button, the server refuses it
    const answers: Record<string, unknown> = { [LIST]: generationList(ECS), [LAYOUT]: NO_LAYOUT };
    await ecsCard(answers);
    answers[LAYOUT] = FORBIDDEN;

    fireEvent.click(screen.getByRole("button", { name: "Generate layout" }));

    const refusal = await screen.findByRole("alert");
    expect(refusal).toHaveTextContent("Failed to group endpoints — your role does not allow that");
    expect(screen.queryByRole("button", { name: "Generate layout" })).toBeNull();
  });

  it("takes a 409 as someone else's grouping: reads the layout again and shows it, with no failure", async () => {
    const answers: Record<string, unknown> = { [LIST]: generationList(ECS), [LAYOUT]: NO_LAYOUT };
    const api = await ecsCard(answers);
    const reread = later();
    let asked = 0;
    // the start is refused, and the read after it finds the layout someone else made
    answers[LAYOUT] = () => (asked++ === 0 ? CONFLICT : reread.arrived);

    fireEvent.click(screen.getByRole("button", { name: "Generate layout" }));

    // still under way until the layout is read again: the button does not come back in between
    await waitFor(() => expect(api.calls(LAYOUT)).toBe(3));
    expect(screen.getByText("Grouping endpoints…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate layout" })).toBeNull();

    reread.send(layout());

    expect(await screen.findByText("1 resource in 1 version, confirmation needed")).toBeInTheDocument();
    expect(screen.queryByText("Failed to group endpoints")).toBeNull();
    expect(screen.queryByRole("button", { name: "Generate layout" })).toBeNull();
    expect(api.calls(LAYOUT)).toBe(3);
    // someone else's layout says nothing about the list: it is not asked again
    expect(api.calls(LIST)).toBe(1);
  });

  it("turns into the page a direct address shows when the start finds the service off the list", async () => {
    const answers: Record<string, unknown> = { [LIST]: generationList(ECS), [LAYOUT]: NO_LAYOUT };
    await ecsCard(answers);
    answers[LAYOUT] = NOT_FOUND;
    answers[LIST] = generationList("customer-core");

    fireEvent.click(screen.getByRole("button", { name: "Generate layout" }));

    expect(await screen.findByText("Page not found.")).toBeInTheDocument();
    expect(screen.queryByText("Failed to group endpoints")).toBeNull();
  });

  it("offers no Generate layout for a service that has a layout already (ADR-0072)", async () => {
    backend({ [LIST]: generationList(ECS), [LAYOUT]: layout() });
    renderPage(<GenerationServicePage />, { path: PATH, route: "/generation/:name" });

    expect(await screen.findByText("1 resource in 1 version, confirmation needed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate layout" })).toBeNull();
  });

  it("shows a layout that failed to load as a failure with Retry, not as a service without one", async () => {
    const answers: Record<string, unknown> = { [LIST]: generationList(ECS), [LAYOUT]: FAILED };
    backend(answers);
    renderPage(<GenerationServicePage />, { path: PATH, route: "/generation/:name" });

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate layout" })).toBeNull();

    answers[LAYOUT] = NO_LAYOUT;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("button", { name: "Generate layout" })).toBeInTheDocument();
  });
});

describe("the targets of a service in the list (ISS-0041)", () => {
  const LIST = "/api/generation/services";
  const LAYOUT = "/api/generation/services/opentelekomcloud-docs%2Fecs/layout";

  /* The card as it ships: generation itself switched off. */
  beforeEach(() => {
    flags.showGenJobs = false;
  });

  /** The browser's Back. */
  function Back() {
    const navigate = useNavigate();
    return (
      <button type="button" onClick={() => navigate(-1)}>
        back
      </button>
    );
  }
  const back = () => fireEvent.click(screen.getByRole("button", { name: "back" }));

  /** The card of ecs at `path`, on a backend whose stored layout is `stored`, with the browser's Back next to it. */
  async function ecsCard(path: string, stored = layout()) {
    const api = backend({ [LIST]: generationList(ECS), [LAYOUT]: stored });
    renderPage(
      <>
        <GenerationServicePage />
        <Location />
        <Back />
      </>,
      { path, route: "/generation/:name" },
    );
    expect(await screen.findByRole("heading", { name: ECS })).toBeInTheDocument();
    return api;
  }

  /** Where every "Edit layout" leads - the header's, and the centre's while the layout waits for confirmation (ISS-0040). */
  function editLayoutTo() {
    const hrefs = screen.getAllByRole("link", { name: "Edit layout" }).map((a) => a.getAttribute("href"));
    expect(new Set(hrefs).size).toBe(1);
    return hrefs[0];
  }

  /** None of what needs generation data: no merged share, no base, no pull request repository, no hint. */
  function expectNoGenerationData() {
    expect(screen.queryByText(/merged/)).toBeNull();
    expect(screen.queryByText("waits on Python SDK")).toBeNull();
    expect(screen.queryByText(/is built on/)).toBeNull();
    expect(screen.queryByText(/Pull requests for this edition/)).toBeNull();
    expect(screen.queryByText(/the layout is already shared with it/)).toBeNull();
  }

  it("offers Python SDK, chosen, and Ansible modules, not connected yet (ADR-0055)", async () => {
    await ecsCard("/generation/opentelekomcloud-docs%2Fecs");

    expect(targetButton("Python SDK")).toHaveAttribute("aria-pressed", "true");
    expect(targetButton("Python SDK")).toHaveTextContent(/^Python SDK$/);
    expect(targetButton("Ansible modules")).toHaveAttribute("aria-pressed", "false");
    expect(targetButton("Ansible modules")).toHaveTextContent("generation not connected yet");
    expectNoGenerationData();
  });

  it("keeps the choice in the address, leaving the default out, and carries it into the layout", async () => {
    await ecsCard("/generation/opentelekomcloud-docs%2Fecs");

    fireEvent.click(targetButton("Ansible modules"));

    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs?target=ansible");
    expect(targetButton("Ansible modules")).toHaveAttribute("aria-pressed", "true");
    expect(editLayoutTo()).toBe("/generation/opentelekomcloud-docs%2Fecs/layout?target=ansible");

    fireEvent.click(targetButton("Python SDK"));

    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs");
    expect(editLayoutTo()).toBe("/generation/opentelekomcloud-docs%2Fecs/layout");
  });

  it("names the choice of target as one, so its buttons are not read out on their own", async () => {
    await ecsCard("/generation/opentelekomcloud-docs%2Fecs");

    const group = screen.getByRole("group", { name: "Target" });
    expect(within(group).getAllByRole("button").map((b) => b.getAttribute("aria-pressed"))).toEqual(["true", "false"]);
  });

  it("makes each switch a step of its own: Back returns to the target before it", async () => {
    await ecsCard("/generation/opentelekomcloud-docs%2Fecs");

    fireEvent.click(targetButton("Ansible modules"));
    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs?target=ansible");

    back();

    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs");
    expect(targetButton("Python SDK")).toHaveAttribute("aria-pressed", "true");
  });

  it("adds no step for the target already chosen: one Back still returns to the target before it", async () => {
    await ecsCard("/generation/opentelekomcloud-docs%2Fecs");
    fireEvent.click(targetButton("Ansible modules"));

    // clicked again, and again: still the same choice, and no step of its own
    fireEvent.click(targetButton("Ansible modules"));
    fireEvent.click(targetButton("Ansible modules"));
    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs?target=ansible");
    expect(targetButton("Ansible modules")).toHaveAttribute("aria-pressed", "true");

    back();

    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs");
    expect(targetButton("Python SDK")).toHaveAttribute("aria-pressed", "true");
  });

  it("tidies an address that names a target there is not, when its default is chosen, without a step", async () => {
    await ecsCard("/generation/opentelekomcloud-docs%2Fecs?target=cobol");

    fireEvent.click(targetButton("Python SDK"));
    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs");
    expect(targetButton("Python SDK")).toHaveAttribute("aria-pressed", "true");

    // the untidy address was replaced, not left behind: Back never returns to it
    fireEvent.click(targetButton("Ansible modules"));
    back();
    back();
    expect(location()).toBe("/generation/opentelekomcloud-docs%2Fecs");
  });

  it("opens on the target the address names", async () => {
    await ecsCard("/generation/opentelekomcloud-docs%2Fecs?target=ansible");

    expect(targetButton("Ansible modules")).toHaveAttribute("aria-pressed", "true");
    expect(targetButton("Python SDK")).toHaveAttribute("aria-pressed", "false");
    // on Ansible modules too, nothing of generation: neither its base nor that it is not connected
    expectNoGenerationData();
  });

  it("opens on Python SDK for a target the address names that there is not", async () => {
    await ecsCard("/generation/opentelekomcloud-docs%2Fecs?target=cobol");

    expect(targetButton("Python SDK")).toHaveAttribute("aria-pressed", "true");
    expect(editLayoutTo()).toBe("/generation/opentelekomcloud-docs%2Fecs/layout");
  });

  it("does not ask for the layout again on a switch: it is the same for every target (ADR-0074)", async () => {
    const api = await ecsCard("/generation/opentelekomcloud-docs%2Fecs");
    const centre = screen.getByRole("region", { name: "Resources" }).textContent;
    const asked = api.calls(LAYOUT);

    fireEvent.click(targetButton("Ansible modules"));

    expect(targetButton("Ansible modules")).toHaveAttribute("aria-pressed", "true");
    expect(api.calls(LAYOUT)).toBe(asked);
    expect(screen.getByRole("region", { name: "Resources" }).textContent).toBe(centre);
  });

  it("says the service did not load when the targets fail, and Retry asks for them again", async () => {
    mockFails.targets = true;
    backend({ [LIST]: generationList(ECS), [LAYOUT]: layout() });
    renderPage(<GenerationServicePage />, {
      path: "/generation/opentelekomcloud-docs%2Fecs",
      route: "/generation/:name",
    });

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Python SDK/ })).toBeNull();

    mockFails.targets = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("button", { name: /^Python SDK/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("Failed to load service")).toBeNull();
  });

  it("says there is no target to generate for when the targets come empty, and Retry asks again", async () => {
    mockFails.noTargets = true;
    backend({ [LIST]: generationList(ECS), [LAYOUT]: layout() });
    renderPage(<GenerationServicePage />, {
      path: "/generation/opentelekomcloud-docs%2Fecs",
      route: "/generation/:name",
    });

    // not a load that failed, and not a blank page
    expect(await screen.findByText("No target to generate for")).toBeInTheDocument();
    expect(screen.queryByText("Failed to load service")).toBeNull();
    expect(screen.queryByRole("region", { name: "Resources" })).toBeNull();

    // the answer was empty, not failed - Retry still asks for the targets again
    mockFails.noTargets = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("button", { name: /^Python SDK/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows a layout that failed while the targets are still on the way", async () => {
    mockFails.holdTargets = true;
    backend({ [LIST]: generationList(ECS), [LAYOUT]: FAILED });
    renderPage(<GenerationServicePage />, {
      path: "/generation/opentelekomcloud-docs%2Fecs",
      route: "/generation/:name",
    });

    expect(await screen.findByText("Failed to load service")).toBeInTheDocument();
  });

  it("offers the choice of target before there is a layout too", async () => {
    await ecsCard("/generation/opentelekomcloud-docs%2Fecs", NO_LAYOUT);

    expect(targetButton("Python SDK")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Generate layout" })).toBeInTheDocument();
  });
});
