import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import LogPane from "./LogPane.svelte";
import { shouldAutoScroll } from "$lib/scroll";
import type { JobState } from "$lib/stores";

const job: JobState = {
  id: 1, project: "wallet", action: "up", done: false, exitCode: null,
  lines: [{ text: "step 1", stream: "stdout" }, { text: "step 2", stream: "stdout" }],
};

describe("shouldAutoScroll", () => {
  it("true when near the bottom", () =>
    expect(shouldAutoScroll({ scrollTop: 880, scrollHeight: 1000, clientHeight: 120 })).toBe(true));
  it("false when scrolled up", () =>
    expect(shouldAutoScroll({ scrollTop: 200, scrollHeight: 1000, clientHeight: 120 })).toBe(false));
});

describe("LogPane", () => {
  it("renders log lines", () => {
    const { getByText } = render(LogPane, { props: { job } });
    expect(getByText(/step 1/)).toBeInTheDocument();
    expect(getByText(/step 2/)).toBeInTheDocument();
  });
});
