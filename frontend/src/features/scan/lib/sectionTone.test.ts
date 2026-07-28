import { describe, expect, it } from "vitest";
import { sectionCountsSummary, sectionTone } from "./sectionTone";

describe("sectionTone: the worst status present wins", () => {
  it("returns empty for no data", () => {
    expect(sectionTone(undefined)).toBe("empty");
    expect(sectionTone(null)).toBe("empty");
  });

  it("returns empty when the section is only ever missing", () => {
    expect(sectionTone({})).toBe("empty");
    expect(sectionTone({ missing: 5 })).toBe("empty");
    expect(sectionTone({ ok: 0, partial: 0 })).toBe("empty");
  });

  it("returns failed when any document failed, regardless of share", () => {
    expect(sectionTone({ ok: 99, failed: 1 })).toBe("failed");
    expect(sectionTone({ ok: 190, partial: 10, failed: 2 })).toBe("failed");
  });

  it("never calls a section ok while a document in it is partial", () => {
    expect(sectionTone({ ok: 199, partial: 1 })).toBe("warn");
    expect(sectionTone({ ok: 95, partial: 5 })).toBe("warn");
    expect(sectionTone({ partial: 10 })).toBe("warn");
  });

  it("does not treat zero counters as occurrences", () => {
    expect(sectionTone({ ok: 10, failed: 0, partial: 0 })).toBe("ok");
  });

  it("ignores missing entirely - an absent section is not a defect", () => {
    expect(sectionTone({ ok: 19, missing: 100 })).toBe("ok");
    expect(sectionTone({ ok: 19, partial: 1, missing: 100 })).toBe("warn");
  });

  it("treats a section that was only skipped as proving nothing", () => {
    expect(sectionTone({ skipped: 4 })).toBe("bad");
  });
});

describe("sectionCountsSummary: the scale behind the colour", () => {
  it("lists the worst status first and drops empty counters", () => {
    expect(sectionCountsSummary({ ok: 16, partial: 9, failed: 2, missing: 33 })).toBe(
      "failed 2 · partial 9 · ok 16 · missing 33",
    );
    expect(sectionCountsSummary({ ok: 5 })).toBe("ok 5");
  });

  it("says so when there is nothing to summarize", () => {
    expect(sectionCountsSummary(undefined)).toBe("no data");
    expect(sectionCountsSummary({})).toBe("no data");
    expect(sectionCountsSummary({ ok: 0 })).toBe("no data");
  });
});
