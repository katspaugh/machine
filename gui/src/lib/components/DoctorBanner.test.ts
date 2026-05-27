import { render, fireEvent, waitFor } from "@testing-library/svelte";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("$lib/tauri", () => ({
  api: { runDoctor: vi.fn() },
}));
import { api } from "$lib/tauri";
import DoctorBanner from "./DoctorBanner.svelte";

describe("DoctorBanner", () => {
  beforeEach(() => vi.clearAllMocks());

  it("hidden when all checks pass", async () => {
    (api.runDoctor as any).mockResolvedValue({
      checks: [{ name: "limactl on PATH", status: "ok", detail: null, hint: null }],
      summary: { checks: 1, fails: 0 },
    });
    const { container } = render(DoctorBanner, {});
    await waitFor(() => expect(api.runDoctor).toHaveBeenCalled());
    expect(container.querySelector(".banner")).toBeNull();
  });

  it("shows failures and expands hints", async () => {
    (api.runDoctor as any).mockResolvedValue({
      checks: [{ name: "SSH_AUTH_SOCK unset", status: "fail", detail: null,
        hint: "start your SSH agent" }],
      summary: { checks: 1, fails: 1 },
    });
    const { getByText, queryByText } = render(DoctorBanner, {});
    await waitFor(() => getByText(/1 check failed/i));
    expect(queryByText("start your SSH agent")).toBeNull(); // collapsed
    await fireEvent.click(getByText(/1 check failed/i));
    expect(getByText("start your SSH agent")).toBeInTheDocument();
  });
});
