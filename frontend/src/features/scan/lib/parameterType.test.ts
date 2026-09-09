import { describe, expect, it } from "vitest";
import { parameterTypeLabel } from "./parameterType";

const p = (over: Record<string, unknown>) =>
  ({ param_type: "String", element_type: null, type_name: null, ...over }) as never;

describe("the type shown for one parameter", () => {
  it("shows a plain type as itself", () => {
    expect(parameterTypeLabel(p({ param_type: "String" }))).toBe("String");
    expect(parameterTypeLabel(p({ param_type: "Object" }))).toBe("Object");
  });

  it("shows what an array holds", () => {
    /* The whole point of splitting the IR: `Array of booleans` had no type of
       its own before and was shown as an object array. */
    expect(parameterTypeLabel(p({ param_type: "Array", element_type: "String" }))).toBe("Array<String>");
    expect(parameterTypeLabel(p({ param_type: "Array", element_type: "Boolean" }))).toBe("Array<Boolean>");
    expect(parameterTypeLabel(p({ param_type: "Array", element_type: "Long" }))).toBe("Array<Long>");
  });

  it("prefers the structure's name over the word Object", () => {
    // `Array<Node>` names a table the reader can go and find; `Array<Object>`
    // does not.
    expect(
      parameterTypeLabel(p({ param_type: "Array", element_type: "Object", type_name: "Node" })),
    ).toBe("Array<Node>");
  });

  it("says only Array when the page never said what it holds", () => {
    expect(parameterTypeLabel(p({ param_type: "Array" }))).toBe("Array");
  });

  it("ignores an element type on something that is not an array", () => {
    expect(
      parameterTypeLabel(p({ param_type: "Object", element_type: "String", type_name: "Node" })),
    ).toBe("Object");
  });
});
