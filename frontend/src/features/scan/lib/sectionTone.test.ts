import { describe, expect, it } from "vitest";
import { sectionTone } from "./sectionTone";

describe("sectionTone (PS10)", () => {
  it("returns empty for no data", () => {
    expect(sectionTone(undefined)).toBe("empty");
    expect(sectionTone(null)).toBe("empty");
  });

  it("returns empty when the non-missing sum is 0", () => {
    expect(sectionTone({})).toBe("empty");
    expect(sectionTone({ missing: 5 })).toBe("empty");
    expect(sectionTone({ ok: 0, partial: 0 })).toBe("empty");
  });

  it("returns failed when any doc failed, regardless of share", () => {
    expect(sectionTone({ ok: 99, failed: 1 })).toBe("failed");
  });

  it("does not treat failed: 0 as failed", () => {
    expect(sectionTone({ ok: 10, failed: 0 })).toBe("ok");
  });

  it("applies the ok-share thresholds: ≥0.95 ok, ≥0.6 warn, else bad", () => {
    expect(sectionTone({ ok: 95, partial: 5 })).toBe("ok");
    expect(sectionTone({ ok: 94, partial: 6 })).toBe("warn");
    expect(sectionTone({ ok: 60, partial: 40 })).toBe("warn");
    expect(sectionTone({ ok: 59, partial: 41 })).toBe("bad");
  });

  it("treats absent ok as zero share", () => {
    expect(sectionTone({ partial: 10 })).toBe("bad");
  });

  it("counts skipped in the denominator", () => {
    expect(sectionTone({ ok: 6, skipped: 4 })).toBe("warn");
  });

  it("excludes missing from the denominator", () => {
    expect(sectionTone({ ok: 19, partial: 1, missing: 100 })).toBe("ok");
  });
});
