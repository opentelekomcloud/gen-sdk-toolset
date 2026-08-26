import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { activationErrorKey, shortError } from "./errors";

describe("shortError: the leading clause is what fits in a registry row", () => {
  it("drops the repository and the provider detail", () => {
    expect(
      shortError(
        "Could not resolve commit for opentelekomcloud-docs/taurusdb@main: GitHub API rate limit exceeded",
      ),
    ).toBe("Could not resolve commit");
    expect(
      shortError(
        "Failed to fetch document content for opentelekomcloud-docs/modelarts: Unexpected content encoding 'none'",
      ),
    ).toBe("Failed to fetch document content");
  });

  it("cuts at the colon when there is no 'for' clause", () => {
    expect(shortError("ingest failed: db exploded")).toBe("ingest failed");
    expect(shortError("could not start job: db connection lost")).toBe("could not start job");
  });

  it("leaves a message that is already short alone", () => {
    expect(shortError("rate limit exceeded")).toBe("rate limit exceeded");
    expect(shortError("")).toBe("");
  });
});

describe("activationErrorKey: a refused switch has to say why", () => {
  it("names the running scan for a 409", () => {
    expect(activationErrorKey(new ApiError(409, "conflict", "Scan job #7 is running"))).toBe(
      "snap.activateConflict",
    );
  });

  it("names the missing snapshot for a 404", () => {
    expect(activationErrorKey(new ApiError(404, "not_found", "Snapshot 3 not found"))).toBe("snap.activateGone");
  });

  it("falls back for any other failure, including one that never reached the API", () => {
    expect(activationErrorKey(new ApiError(500, "internal_error", "boom"))).toBe("snap.activateFailed");
    expect(activationErrorKey(new TypeError("network down"))).toBe("snap.activateFailed");
  });
});
