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
