import { describe, expect, it } from "vitest";

/**
 * index.css switches Tailwind's palette off and offers only the ODS-backed
 * colours (issue #135). Tailwind drops a class it does not know without a
 * word, so `bg-gray-100` would build clean and paint nothing - or, worse, a
 * hand-written hex would paint a colour that ignores light/dark mode. This
 * suite is the check Tailwind does not do.
 */

/* Every source file as text; tests are left out, and so is the schema
   generated from the backend, which is not ours to restyle. */
const SOURCES = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>(["./**/*.{ts,tsx}", "!./**/*.test.{ts,tsx}", "!./**/schema.gen.ts"], {
      query: "?raw",
      import: "default",
      eager: true,
    }),
  ),
);

const PALETTE =
  "slate|gray|zinc|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|white|black";
const RAW_PALETTE_CLASS = new RegExp(
  `(?<![\\w-])(?:[a-z-]+:)*(?:bg|text|border|ring|divide|outline|decoration|fill|stroke|from|via|to|placeholder|caret|accent|shadow)-(?:${PALETTE})(?:-\\d+)?(?:/\\d+)?(?![\\w-])`,
  "g",
);
/* `(?<!\w)`: "python-t-cloud#131" is a pull request, not a colour */
const RAW_COLOUR_VALUE = /(?:(?<!\w)#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\()/g;

/** Hits per file, with comments stripped so a note may still name a colour. */
function findings(pattern: RegExp): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const [file, text] of Object.entries(SOURCES)) {
    const hits = text.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "").match(pattern);
    if (hits) out[file] = hits;
  }
  return out;
}

describe("colours come from the ODS tokens", () => {
  it("uses no Tailwind palette class", () => {
    expect(findings(RAW_PALETTE_CLASS)).toEqual({});
  });

  it("hard-codes no colour value", () => {
    expect(findings(RAW_COLOUR_VALUE)).toEqual({});
  });

  it("still sees the source tree", () => {
    /* guards the two checks above against passing on an empty file list */
    expect(Object.keys(SOURCES).length).toBeGreaterThan(20);
  });
});
