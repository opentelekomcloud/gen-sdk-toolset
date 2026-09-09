import type { Parameter } from "../../../shared/api/types";

/**
 * The complete type of a parameter, as one string.
 *
 * The IR splits an array from what it holds, because `Array of booleans` had no
 * composite type to land on and used to be filed as an object array. The reader
 * still wants it in one piece, so the two halves are joined back here rather
 * than in every component that shows a type.
 *
 * A structure name wins over the element kind: `Array<Node>` says more than
 * `Array<Object>`, and it is the name a reader can go and look up.
 */
export function parameterTypeLabel(p: Pick<Parameter, "param_type" | "element_type" | "type_name">): string {
  if (p.param_type !== "Array") return p.param_type;
  const element = p.type_name ?? p.element_type;
  return element ? `Array<${element}>` : "Array";
}
