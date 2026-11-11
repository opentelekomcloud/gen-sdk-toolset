import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import { useLocation } from "react-router";
import { alertNamed, backend, FAILED, later, pollAgain, refresh, renderPage } from "../../../test/render";
import { keys } from "../api/queries";
import { AttentionBand } from "./AttentionBand";

/** Where the band navigated to. */
function Location() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}

const SCAN_RULES = [{ code: "failed", panel: "scan", label: "failed and hold no data", count: 2 }];

function band() {
  return renderPage(
    <>
      <AttentionBand />
      <Location />
    </>,
    { path: "/scan", route: "*", seed: [[keys.attention, SCAN_RULES]] },
  );
}

const location = () => screen.getByTestId("location").textContent;

describe("the attention band shared by the panels", () => {
  it("carries the Generation rules next to the scan rules, tagged by panel", async () => {
    band();

    expect(await screen.findByRole("button", { name: /generated, waiting for review/ })).toHaveTextContent(
      "1generated, waiting for reviewgeneration",
    );
    expect(screen.getByRole("button", { name: /generation failed — LLM unavailable/ })).toHaveTextContent(
      "1generation failed — LLM unavailablegeneration",
    );
    expect(screen.getByRole("button", { name: /failed and hold no data/ })).toHaveTextContent(
      "2failed and hold no datascan",
    );
  });

  it("leads a Generation rule to the Generation list on its filter", async () => {
    band();

    fireEvent.click(await screen.findByRole("button", { name: /waiting for review/ }));
    expect(location()).toBe("/generation?filter=review");

    fireEvent.click(screen.getByRole("button", { name: /generation failed/ }));
    expect(location()).toBe("/generation?filter=failed");
  });

  it("still leads a scan rule to the filtered registry", async () => {
    band();

    fireEvent.click(await screen.findByRole("button", { name: /failed and hold no data/ }));

    expect(location()).toBe("/scan?rule=failed");
  });
});

describe("the attention band when a panel's rules fail to load", () => {
  afterEach(() => vi.unstubAllGlobals());

  const ATTENTION = "/api/scan/attention";
  const SCAN_FAILED = "Could not load the Scan rules — this list may be incomplete.";

  /** The scan rules request fails; what `seed` does not hold, the band has to fetch. */
  function bandWithScanDown(seed: [readonly unknown[], unknown][] = []) {
    const answers: Record<string, unknown> = { [ATTENTION]: FAILED };
    backend(answers);
    return { answers, ...renderPage(<AttentionBand />, { path: "/scan", route: "*", seed }) };
  }

  it("keeps the Generation rules and names the panel that did not load", async () => {
    bandWithScanDown();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the Scan rules");
    expect(screen.getByRole("button", { name: /generated, waiting for review/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generation failed — LLM unavailable/ })).toBeInTheDocument();
  });

  it("does not pass for all clear when the rules that loaded are empty", async () => {
    bandWithScanDown([[keys.genAttention, []]]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the Scan rules");
    expect(screen.queryByText(/All caught up/)).not.toBeInTheDocument();
  });

  it("replaces only the scan rules when they fail to refresh: the Generation rules stay", async () => {
    const { client } = bandWithScanDown([[keys.attention, SCAN_RULES]]);
    expect(await screen.findByRole("button", { name: /failed and hold no data/ })).toBeInTheDocument();

    await refresh(client, keys.attention);

    const failure = await alertNamed(SCAN_FAILED);
    expect(within(failure).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /failed and hold no data/ })).toBeNull();
    expect(screen.getByRole("button", { name: /generated, waiting for review/ })).toBeInTheDocument();
  });

  it("brings the scan rules back on Retry", async () => {
    const { answers } = bandWithScanDown();
    const failure = await alertNamed(SCAN_FAILED);

    answers[ATTENTION] = SCAN_RULES;
    fireEvent.click(within(failure).getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("button", { name: /failed and hold no data/ })).toBeInTheDocument();
    expect(screen.queryByText(SCAN_FAILED)).toBeNull();
  });

  it("says it is loading while a Retry runs, the Generation rules still there", async () => {
    const { answers } = bandWithScanDown();
    const failure = await alertNamed(SCAN_FAILED);

    const rules = later();
    answers[ATTENTION] = rules.arrived;
    fireEvent.click(within(failure).getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Loading the Scan rules…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generated, waiting for review/ })).toBeInTheDocument();
    rules.send(SCAN_RULES);
    expect(await screen.findByRole("button", { name: /failed and hold no data/ })).toBeInTheDocument();
  });

  /* A first load that failed stays failed while it is asked again (ADR-0081):
     TanStack moves such a query back to "pending", which would hide the whole
     band, the Generation rules with it, on every periodic refresh. */
  it("keeps the band, the failure and the Generation rules while the periodic refresh asks again", async () => {
    const { answers, client } = bandWithScanDown();
    const failure = await alertNamed(SCAN_FAILED);

    const rules = later();
    answers[ATTENTION] = rules.arrived;
    await pollAgain(client, keys.attention);

    expect(screen.getByText(SCAN_FAILED).closest("[role=alert]")).toBe(failure);
    expect(screen.getByRole("button", { name: /generated, waiting for review/ })).toBeInTheDocument();
    rules.send(SCAN_RULES);
    expect(await screen.findByRole("button", { name: /failed and hold no data/ })).toBeInTheDocument();
    expect(screen.queryByText(SCAN_FAILED)).toBeNull();
  });
});
