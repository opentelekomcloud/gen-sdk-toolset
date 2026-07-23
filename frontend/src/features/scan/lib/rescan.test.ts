import { describe, expect, it } from "vitest";
import { RESCAN_META } from "./rescan";
import { en } from "../../../shared/i18n/en";
import { de } from "../../../shared/i18n/de";

describe("RESCAN_META", () => {
  it("covers all four server-side reasons", () => {
    expect(Object.keys(RESCAN_META).sort()).toEqual(["drift", "partial", "retry", "version"]);
  });

  it("only retry carries the destructive tone", () => {
    expect(RESCAN_META.retry.destructiveTone).toBe(true);
    expect(RESCAN_META.partial.destructiveTone).toBe(false);
    expect(RESCAN_META.version.destructiveTone).toBe(false);
    expect(RESCAN_META.drift.destructiveTone).toBe(false);
  });

  it("labels every reason in both dictionaries; version embeds the scanner version", () => {
    for (const meta of Object.values(RESCAN_META)) {
      expect(en[meta.labelKey]).toBeTruthy();
      expect(de[meta.labelKey]).toBeTruthy();
    }
    expect(RESCAN_META.version.labelKey).toBe("rescan.version");
    expect(en[RESCAN_META.version.labelKey]).toContain("{v}");
    expect(de[RESCAN_META.version.labelKey]).toContain("{v}");
  });
});
