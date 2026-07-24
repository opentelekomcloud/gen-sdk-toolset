import { describe, expect, it } from "vitest";
import { CONFIG, SECTIONS, sectionLabelKey } from "./constants";
import { en } from "../../shared/i18n/en";
import { de } from "../../shared/i18n/de";

describe("sections contract (PS1)", () => {
  it("has exactly 7 sections in fixed order", () => {
    expect(SECTIONS).toHaveLength(7);
    expect(SECTIONS[0]).toBe("path_params");
    expect(SECTIONS[6]).toBe("example_response");
  });

  it("labels every section in both dictionaries", () => {
    for (const s of SECTIONS) {
      expect(sectionLabelKey(s)).toBe(`section.${s}`);
      expect(en[sectionLabelKey(s)]).toBeTruthy();
      expect(de[sectionLabelKey(s)]).toBeTruthy();
    }
  });
});

describe("CONFIG.identity", () => {
  it("falls back to anonymous without env config", () => {
    expect(typeof CONFIG.identity).toBe("string");
    expect(CONFIG.identity.length).toBeGreaterThan(0);
  });
});
