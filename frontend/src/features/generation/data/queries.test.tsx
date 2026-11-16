import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useGenerationLayout } from "./queries";
import { keys } from "../../scan/api/queries";
import { ApiError } from "../../scan/api/client";
import type { Layout } from "../../../shared/api/types";
import { layout } from "../../../test/fixtures";
import { backend } from "../../../test/render";

const NAME = "opentelekomcloud-docs/ecs";
const PATH = "/api/generation/services/opentelekomcloud-docs%2Fecs/layout";

afterEach(() => vi.unstubAllGlobals());

function readLayout(options?: { enabled?: boolean }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, ...renderHook(() => useGenerationLayout(NAME, options), { wrapper }) };
}

describe("useGenerationLayout", () => {
  it("reads the layout of the service from the backend, under its key in the registry", async () => {
    const stored = layout();
    const api = backend({ [PATH]: stored });

    const { qc, result } = readLayout();

    await waitFor(() => expect(result.current.data).toEqual(stored));
    expect(api.calls(PATH)).toBe(1);
    expect(qc.getQueryData<Layout>(keys.genLayout(NAME))).toEqual(stored);
  });

  it("serves a service whose grouping has not run as a layout, not as a failure", async () => {
    backend({ [PATH]: layout({ has_layout: false, versions: [] }) });

    const { result } = readLayout();

    await waitFor(() => expect(result.current.data?.has_layout).toBe(false));
    expect(result.current.isError).toBe(false);
  });

  it("fails for a repository off the Generation list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ error: { code: "not_found", message: "no such service" } }), { status: 404 })),
    );

    const { result } = readLayout();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).status).toBe(404);
  });

  it("asks nothing while it is held back, as for a repository off the list", async () => {
    const api = backend({ [PATH]: layout() });

    const { qc, result } = readLayout({ enabled: false });

    // an enabled query is fetching from its first render; a refetch of every query skips a held one
    expect(result.current.fetchStatus).toBe("idle");
    await qc.refetchQueries();
    expect(api.calls(PATH)).toBe(0);
    expect(result.current.data).toBeUndefined();
  });
});
