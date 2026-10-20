import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { I18nProvider } from "../i18n";
import { SearchInput } from "./SearchInput";
import { useUrlSearch } from "./useUrlSearch";

function Harness() {
  const { q, input, setInput } = useUrlSearch();
  const { search } = useLocation();
  return (
    <>
      <SearchInput value={input} onChange={setInput} />
      <output data-testid="q">{q}</output>
      <output data-testid="search">{search}</output>
    </>
  );
}

function harness(path = "/list") {
  return render(
    <I18nProvider>
      <MemoryRouter initialEntries={[path]}>
        <Harness />
      </MemoryRouter>
    </I18nProvider>,
  );
}

const field = () => screen.getByPlaceholderText("Filter services…");
const search = () => screen.getByTestId("search").textContent;

describe("the search kept in the address", () => {
  it("opens with the text the address holds", () => {
    harness("/list?q=vpc&status=failed");

    expect(field()).toHaveValue("vpc");
    expect(screen.getByTestId("q")).toHaveTextContent("vpc");
  });

  it("writes the text into the address once typing stops, keeping the other parameters", async () => {
    harness("/list?status=failed");

    fireEvent.change(field(), { target: { value: "core" } });

    expect(field()).toHaveValue("core");
    expect(search()).toBe("?status=failed");
    await waitFor(() => expect(search()).toBe("?status=failed&q=core"));
    expect(screen.getByTestId("q")).toHaveTextContent("core");
  });

  it("drops the parameter when the field is cleared", async () => {
    harness("/list?q=vpc");

    fireEvent.change(field(), { target: { value: "" } });

    await waitFor(() => expect(search()).toBe(""));
  });
});
