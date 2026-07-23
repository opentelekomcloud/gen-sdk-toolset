import { describe, expect, it } from "vitest";
import { fmtGenAt, genBreakdown, isLatest, shortCommit, structPct } from "./generation";
import type { Generation } from "../api/types.local";

describe("shortCommit", () => {
  it("shows the git-style 7-char short form of the full stored hash", () => {
    expect(shortCommit("a1b2c3d4e5f60718293a4b5c6d7e8f9012345678")).toBe("a1b2c3d");
  });
});

describe("fmtGenAt", () => {
  it("renders — for missing timestamps", () => {
    expect(fmtGenAt(null)).toBe("—");
    expect(fmtGenAt(undefined)).toBe("—");
  });

  it("formats in the viewer's locale (en-GB slashes, de-DE dots)", () => {
    const iso = "2026-07-23T09:15:00Z";
    expect(fmtGenAt(iso, "en-GB")).toMatch(/^\d{2}\/\d{2}\/\d{4}, \d{2}:\d{2}$/);
    expect(fmtGenAt(iso, "de-DE")).toMatch(/^\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}$/);
  });
});

describe("structPct", () => {
  it("maps the DB 0..1 float to a rounded percent, passing null through", () => {
    expect(structPct(null)).toBeNull();
    expect(structPct(0.945)).toBe(95);
    expect(structPct(0.946)).toBe(95);
    expect(structPct(1)).toBe(100);
    expect(structPct(0)).toBe(0);
  });
});

describe("genBreakdown", () => {
  it("projects the persisted status counts into the OverallBar shape", () => {
    const g = { ok_count: 40, partial_count: 2, failed_count: 1, unsupported_count: 3 } as Generation;
    expect(genBreakdown(g)).toEqual({ ok: 40, partial: 2, failed: 1, unsupported: 3 });
  });
});

describe("isLatest", () => {
  it("treats unknown ids as latest (no stale-generation warning without data)", () => {
    expect(isLatest(null, 5)).toBe(true);
    expect(isLatest(5, null)).toBe(true);
  });

  it("compares ids when both are known", () => {
    expect(isLatest(5, 5)).toBe(true);
    expect(isLatest(4, 5)).toBe(false);
  });
});
