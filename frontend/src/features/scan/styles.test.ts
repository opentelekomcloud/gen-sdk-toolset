import { describe, expect, it } from "vitest";
import { chipCls, DOC_STATUS_CLS, methodCls, SCAN_PILL, SECTION_STATUS_CLS, structOkCls, TONE_BG } from "./styles";

describe("typed class maps", () => {
  it("covers every scan status with a label and class", () => {
    for (const v of Object.values(SCAN_PILL)) {
      expect(v.label).toBeTruthy();
      expect(v.cls).toBeTruthy();
    }
  });

  it("covers doc/section statuses and tones", () => {
    expect(Object.keys(DOC_STATUS_CLS)).toHaveLength(4);
    expect(Object.keys(SECTION_STATUS_CLS)).toHaveLength(5);
    expect(Object.keys(TONE_BG)).toHaveLength(5);
  });
});

describe("methodCls", () => {
  it("maps known methods and falls back for exotic ones", () => {
    expect(methodCls("GET")).toContain("blue");
    expect(methodCls("DELETE")).toContain("red");
    expect(methodCls("PROPFIND")).toBe("bg-gray-100 text-gray-600");
  });
});

describe("structOkCls thresholds", () => {
  it("null → muted, ≥90 ok, ≥60 warn, else bad", () => {
    expect(structOkCls(null)).toContain("gray");
    expect(structOkCls(90)).toContain("emerald");
    expect(structOkCls(89)).toContain("amber");
    expect(structOkCls(60)).toContain("amber");
    expect(structOkCls(59)).toContain("red");
  });
});

describe("chipCls", () => {
  it("switches between active and inactive styles", () => {
    expect(chipCls(true)).toContain("bg-brand");
    expect(chipCls(false)).toContain("bg-white");
  });
});
