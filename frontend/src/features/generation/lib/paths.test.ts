import { describe, expect, it } from "vitest";
import type { GenTarget } from "../data/types";
import { chosenTarget } from "./paths";

const PYTHON: GenTarget = { id: "python", label: "Python SDK", live: true, base: null, repo: "py" };
const ANSIBLE: GenTarget = { id: "ansible", label: "Ansible modules", live: false, base: "python", repo: "ans" };
const TARGETS = [PYTHON, ANSIBLE];

describe("chosenTarget", () => {
  it("chooses the target the address names", () => {
    expect(chosenTarget(TARGETS, "ansible")).toEqual({ target: ANSIBLE, defaultTarget: PYTHON });
  });

  it("falls back to the first target when the address names none, or one there is not (ADR-0055)", () => {
    expect(chosenTarget(TARGETS, null)).toEqual({ target: PYTHON, defaultTarget: PYTHON });
    expect(chosenTarget(TARGETS, "cobol")).toEqual({ target: PYTHON, defaultTarget: PYTHON });
  });

  it("has nothing to choose without targets", () => {
    expect(chosenTarget([], "python")).toBeNull();
  });
});
