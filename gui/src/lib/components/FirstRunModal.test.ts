import { render, fireEvent } from "@testing-library/svelte";
import { describe, it, expect, vi } from "vitest";
import FirstRunModal from "./FirstRunModal.svelte";

describe("FirstRunModal", () => {
  it("disables submit until name + repo are valid", async () => {
    const onSubmit = vi.fn();
    const { getByRole, getByLabelText } = render(FirstRunModal, {
      props: { profiles: ["cypress", "go"], onSubmit, onSkip: () => {} },
    });
    const submit = getByRole("button", { name: /create/i });
    expect(submit).toBeDisabled();
    await fireEvent.input(getByLabelText(/name/i), { target: { value: "myproj" } });
    expect(submit).toBeDisabled(); // repo still empty
    await fireEvent.input(getByLabelText(/repo/i),
      { target: { value: "git@github.com:me/x.git" } });
    expect(submit).not.toBeDisabled();
    await fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith({
      name: "myproj", repo: "git@github.com:me/x.git", profiles: [],
    });
  });

  it("rejects an invalid name", async () => {
    const { getByRole, getByLabelText } = render(FirstRunModal, {
      props: { profiles: [], onSubmit: () => {}, onSkip: () => {} },
    });
    await fireEvent.input(getByLabelText(/name/i), { target: { value: "Bad_Name" } });
    await fireEvent.input(getByLabelText(/repo/i), { target: { value: "x" } });
    expect(getByRole("button", { name: /create/i })).toBeDisabled();
  });
});
