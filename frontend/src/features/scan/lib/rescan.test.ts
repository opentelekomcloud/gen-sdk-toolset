import { describe, expect, it } from "vitest";
import { RESCAN_META } from "./rescan";

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

  it("labels every reason; version embeds the current scanner version", () => {
    expect(RESCAN_META.version.label("3.2.0")).toBe("Rescan · v3.2.0");
    expect(RESCAN_META.retry.label("3.2.0")).toBe("Retry");
    expect(RESCAN_META.partial.label("3.2.0")).toBe("Rescan · incomplete");
    expect(RESCAN_META.drift.label("3.2.0")).toBe("Rescan · docs changed");
  });
});
