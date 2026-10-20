import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeProvider, useTheme } from ".";

/** Shows the mode and offers the one switch the header offers. */
function Probe() {
  const { mode, setMode } = useTheme();
  return (
    <button type="button" onClick={() => setMode(mode === "dark" ? "light" : "dark")}>
      {mode}
    </button>
  );
}

/** An OS that prefers dark, or not. */
function osPrefersDark(dark: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) => ({ matches: dark && query.includes("dark"), media: query }) as MediaQueryList,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("light and dark mode", () => {
  it("follows the operating system until the user picks one", () => {
    osPrefersDark(true);

    render(<ThemeProvider><Probe /></ThemeProvider>);

    expect(screen.getByRole("button")).toHaveTextContent("dark");
    expect(document.body.dataset.mode).toBe("dark");
    expect(document.documentElement.dataset.mode).toBe("dark");
  });

  it("does not store the operating system's mode, so a later OS switch still shows", () => {
    osPrefersDark(true);

    render(<ThemeProvider><Probe /></ThemeProvider>);

    expect(localStorage.getItem("panel.mode")).toBeNull();
  });

  it("remembers a pick over the operating system", () => {
    osPrefersDark(true);
    const { unmount } = render(<ThemeProvider><Probe /></ThemeProvider>);

    fireEvent.click(screen.getByRole("button"));
    expect(document.body.dataset.mode).toBe("light");
    unmount();

    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByRole("button")).toHaveTextContent("light");
  });
});
