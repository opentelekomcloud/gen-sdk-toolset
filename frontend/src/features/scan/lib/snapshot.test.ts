import { describe, expect, it } from "vitest";
import { fmtSnapshotAt, snapshotBreakdown, isLatest, shortCommit, structPct } from "./snapshot";
import type { Snapshot } from "../../../shared/api/types";

describe("shortCommit", () => {
  it("shows the git-style 7-char short form of the full stored hash", () => {
    expect(shortCommit("a1b2c3d4e5f60718293a4b5c6d7e8f9012345678")).toBe("a1b2c3d");
  });
});

describe("fmtSnapshotAt", () => {
  it("renders — for missing timestamps", () => {
    expect(fmtSnapshotAt(null)).toBe("—");
    expect(fmtSnapshotAt(undefined)).toBe("—");
  });

  it("formats in the viewer's locale (en-GB slashes, de-DE dots)", () => {
    const iso = "2026-07-23T09:15:00Z";
    expect(fmtSnapshotAt(iso, "en-GB")).toMatch(/^\d{2}\/\d{2}\/\d{4}, \d{2}:\d{2}$/);
    expect(fmtSnapshotAt(iso, "de-DE")).toMatch(/^\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}$/);
  });
});

describe("structPct", () => {
  it("maps the DB 0..1 float to a percent, never rounding up", () => {
    expect(structPct(null)).toBeNull();
    expect(structPct(0.945)).toBe(94);
    expect(structPct(0.946)).toBe(94);
    expect(structPct(1)).toBe(100);
    expect(structPct(0)).toBe(0);
    // the value that made a partial scan read as "100%"
    expect(structPct(0.9993131868131868)).toBe(99);
  });
});

describe("snapshotBreakdown", () => {
  it("projects the persisted status counts into the OverallBar shape", () => {
    const g = { ok_count: 40, partial_count: 2, failed_count: 1, unsupported_count: 3 } as Snapshot;
    expect(snapshotBreakdown(g)).toEqual({ ok: 40, partial: 2, failed: 1, unsupported: 3 });
  });
});

describe("isLatest", () => {
  it("treats unknown ids as latest (no stale-snapshot warning without data)", () => {
    expect(isLatest(null, 5)).toBe(true);
    expect(isLatest(5, null)).toBe(true);
  });

  it("compares ids when both are known", () => {
    expect(isLatest(5, 5)).toBe(true);
    expect(isLatest(4, 5)).toBe(false);
  });
});
