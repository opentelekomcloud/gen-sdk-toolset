/**
 * Test setup for every suite.
 *
 * `cleanup` is registered by hand because this project does not enable Vitest's
 * globals - without it, one test's DOM stays mounted while the next one runs
 * and queries start matching the previous render.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

/* jsdom has no matchMedia, and the ODS header sizes itself with it. Every
   query answers "no match": jsdom reports a 1024px-wide window, so this is
   the desktop layout the header would pick anyway. */
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

/* jsdom has no ResizeObserver either; the ODS dialog watches its own height
   with one. Nothing in jsdom ever resizes, so an observer that never fires is
   exactly what a real one would do here. */
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
