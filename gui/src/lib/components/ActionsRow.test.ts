import { render, fireEvent } from "@testing-library/svelte";
import { describe, it, expect, vi } from "vitest";
import ActionsRow from "./ActionsRow.svelte";

const base = {
  project: "wallet",
  onRun: vi.fn(),
  onConfirm: vi.fn(),
  onCancel: vi.fn(),
};

describe("ActionsRow", () => {
  it("fires onRun for up directly", async () => {
    const onRun = vi.fn();
    const { getByRole } = render(ActionsRow, { props: { ...base, onRun, activeJob: null } });
    await fireEvent.click(getByRole("button", { name: /^up$/i }));
    expect(onRun).toHaveBeenCalledWith("up");
  });

  it("requests confirmation for destroy", async () => {
    const onConfirm = vi.fn();
    const { getByRole } = render(ActionsRow, { props: { ...base, onConfirm, activeJob: null } });
    await fireEvent.click(getByRole("button", { name: /^destroy$/i }));
    expect(onConfirm).toHaveBeenCalledWith("destroy");
  });

  it("collapses to Cancel while a job runs", () => {
    const { getByRole, queryByRole } = render(ActionsRow, {
      props: { ...base, activeJob: { id: 1, project: "wallet", action: "up",
        lines: [], done: false, exitCode: null } },
    });
    expect(getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    expect(queryByRole("button", { name: /^up$/i })).toBeNull();
  });
});
