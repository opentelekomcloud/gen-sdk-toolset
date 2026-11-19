/**
 * Test setup for every suite.
 *
 * `cleanup` is registered by hand because this project does not enable Vitest's
 * globals - without it, one test's DOM stays mounted while the next one runs
 * and queries start matching the previous render. The mock's failure switches
 * are reset the same way, so a test that sets one cannot leak it.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { resetMockFails } from "./mockFails";

afterEach(cleanup);
afterEach(resetMockFails);
