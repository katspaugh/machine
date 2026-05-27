import { render, fireEvent } from "@testing-library/svelte";
import { describe, it, expect, vi } from "vitest";
import ConfirmDestroyModal from "./ConfirmDestroyModal.svelte";

describe("ConfirmDestroyModal", () => {
  it("disables confirm until the name matches", async () => {
    const onConfirm = vi.fn();
    const { getByRole, getByLabelText } = render(ConfirmDestroyModal, {
      props: { project: "wallet", action: "destroy", onConfirm, onCancel: () => {} },
    });
    const btn = getByRole("button", { name: /destroy/i });
    expect(btn).toBeDisabled();
    await fireEvent.input(getByLabelText(/type the project name/i),
      { target: { value: "wallet" } });
    expect(btn).not.toBeDisabled();
    await fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("does not confirm on a wrong name", async () => {
    const onConfirm = vi.fn();
    const { getByRole, getByLabelText } = render(ConfirmDestroyModal, {
      props: { project: "wallet", action: "rebuild", onConfirm, onCancel: () => {} },
    });
    await fireEvent.input(getByLabelText(/type the project name/i),
      { target: { value: "wrong" } });
    expect(getByRole("button", { name: /rebuild/i })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
