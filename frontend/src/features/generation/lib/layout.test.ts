import { describe, expect, it } from "vitest";
import { movable, nameProblem } from "./layout";

describe("nameProblem (ADR-0065)", () => {
  it.each(["invoices", "v2_invoices", "a", "r_1"])("takes the package name %s", (name) => {
    expect(nameProblem(name, [])).toBeNull();
  });

  it.each(["", "Invoices", "1st", "_x", "in-voices", "in voices", "rechnungsé"])("refuses %j", (name) => {
    expect(nameProblem(name, [])).toBe("invalid");
  });

  it("refuses a name its version already has, and says a malformed one is malformed first", () => {
    expect(nameProblem("invoices", ["payments", "invoices"])).toBe("taken");
    expect(nameProblem("Invoices", ["Invoices"])).toBe("invalid");
  });
});

describe("movable (ADR-0064)", () => {
  const invoices = { id: 1, version: "v1" };

  it("moves an endpoint between resources of one version, and not across versions", () => {
    expect(movable({ resource: 2, version: "v1" }, invoices)).toBe(true);
    expect(movable({ resource: 3, version: "v2" }, invoices)).toBe(false);
  });

  it("moves nothing into the resource the endpoint is in", () => {
    expect(movable({ resource: 1, version: "v1" }, invoices)).toBe(false);
  });

  it("moves an unassigned endpoint into its own version only", () => {
    expect(movable({ resource: null, version: "v1" }, invoices)).toBe(true);
    expect(movable({ resource: null, version: "v2" }, invoices)).toBe(false);
  });

  it("moves an endpoint without a version into any version", () => {
    expect(movable({ resource: null, version: null }, invoices)).toBe(true);
    expect(movable({ resource: null, version: null }, { id: 9, version: "v3" })).toBe(true);
  });
});
