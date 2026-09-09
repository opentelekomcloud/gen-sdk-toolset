import { describe, expect, it } from "vitest";
import { SECTIONS, sectionLabelKey } from "./constants";
import { en } from "../../shared/i18n/en";
import { de } from "../../shared/i18n/de";

describe("sections contract", () => {
  it("has exactly 8 sections in fixed order", () => {
    expect(SECTIONS).toHaveLength(8);
    expect(SECTIONS[0]).toBe("path_params");
    expect(SECTIONS[7]).toBe("status_codes");
  });

  it("holds no duplicates, so the strip renders one square per section", () => {
    expect(new Set(SECTIONS).size).toBe(SECTIONS.length);
  });

  it("labels every section in both dictionaries", () => {
    for (const s of SECTIONS) {
      expect(sectionLabelKey(s)).toBe(`section.${s}`);
      expect(en[sectionLabelKey(s)]).toBeTruthy();
      expect(de[sectionLabelKey(s)]).toBeTruthy();
    }
  });
});
