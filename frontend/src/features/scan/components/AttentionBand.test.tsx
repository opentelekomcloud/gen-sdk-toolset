import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { useLocation } from "react-router";
import { renderPage } from "../../../test/render";
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
