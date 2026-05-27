import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import DetailPanel from "./DetailPanel.svelte";
import type { ProjectStatus } from "$lib/tauri";

const proj: ProjectStatus = {
  name: "wallet", status: "Running", uptime_seconds: 8040, cpu_percent: 2.1,
  mem_used_bytes: 1_932_735_283, mem_total_bytes: 8_589_934_592,
  primary_repo: "wallet", branch: "main", idle_seconds: 180,
  ports: [3000], profiles: ["cypress"], repos: [],
};

describe("DetailPanel", () => {
  it("shows the project header and status", () => {
    const { getByText } = render(DetailPanel, {
      props: { project: proj, jobs: new Map(),
        onRun: () => {}, onConfirm: () => {}, onCancel: () => {} },
    });
    expect(getByText("wallet")).toBeInTheDocument();
    expect(getByText(/Running/)).toBeInTheDocument();
    expect(getByText(/2h 14m/)).toBeInTheDocument(); // uptime 8040s
  });
});
