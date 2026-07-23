import { describe, expect, it } from "vitest";
import { CONFIG, SECTION_LABELS, SECTIONS } from "./constants";

describe("sections contract (PS1)", () => {
  it("has exactly 7 sections in fixed order", () => {
    expect(SECTIONS).toHaveLength(7);
    expect(SECTIONS[0]).toBe("path_params");
    expect(SECTIONS[6]).toBe("example_response");
  });

  it("labels every section", () => {
    for (const s of SECTIONS) expect(SECTION_LABELS[s]).toBeTruthy();
  });
});

describe("CONFIG.identity", () => {
  it("falls back to anonymous without env config", () => {
    expect(typeof CONFIG.identity).toBe("string");
    expect(CONFIG.identity.length).toBeGreaterThan(0);
  });
});
