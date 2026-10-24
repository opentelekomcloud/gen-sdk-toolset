import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderPage } from "../../../test/render";
import type { ServiceDetail } from "../../../shared/api/types";
import { ExcludeModal } from "./ExcludeModal";

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: { access_token: "", profile: { preferred_username: "ada@otc.test" } },
    isAuthenticated: true,
    isLoading: false,
    signinRedirect: vi.fn(),
    signoutRedirect: vi.fn(),
  }),
}));

const SERVICE = { name: "opentelekomcloud-docs/ecs", rescan_reason: null } as unknown as ServiceDetail;

function openDialog() {
  const onConfirm = vi.fn();
  const onClose = vi.fn();
  renderPage(<ExcludeModal service={SERVICE} onConfirm={onConfirm} onClose={onClose} />);
  return { onConfirm, onClose };
}

describe("excluding a service asks for a reason", () => {
  it("opens as a dialog that names the service and who will be recorded", async () => {
    openDialog();

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/opentelekomcloud-docs\/ecs/)).toBeInTheDocument();
    expect(screen.getByText(/ada@otc\.test/)).toBeInTheDocument();
  });

  it("will not exclude without a reason", async () => {
    const { onConfirm } = openDialog();

    const confirm = await screen.findByRole("button", { name: "Exclude service" });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } });
    expect(confirm).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("excludes with the reason as typed, trimmed", async () => {
    const { onConfirm } = openDialog();

    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "  retired upstream  " } });
    fireEvent.click(screen.getByRole("button", { name: "Exclude service" }));

    expect(onConfirm).toHaveBeenCalledWith("retired upstream");
  });

  it("closes on cancel without excluding", async () => {
    const { onConfirm, onClose } = openDialog();

    fireEvent.click((await screen.findAllByRole("button", { name: "Cancel" }))[0]);

    expect(onClose).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
