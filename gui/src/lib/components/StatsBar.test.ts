import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import StatsBar from "./StatsBar.svelte";
import type { ProjectStatus } from "$lib/tauri";

const running: ProjectStatus = {
  name: "wallet", status: "Running", uptime_seconds: 8040, cpu_percent: 2.1,
  mem_used_bytes: 1_932_735_283, mem_total_bytes: 8_589_934_592,
  primary_repo: "wallet", branch: "main", idle_seconds: 180,
  ports: [3000, 5173], profiles: ["cypress"], repos: [],
};

describe("StatsBar", () => {
  it("renders formatted stats", () => {
    const { getByText } = render(StatsBar, { props: { project: running } });
    expect(getByText("2%")).toBeInTheDocument();
    expect(getByText("1.8 / 8 GB")).toBeInTheDocument();
    expect(getByText("3m")).toBeInTheDocument();         // idle 180s
    expect(getByText("3000, 5173")).toBeInTheDocument();
  });

  it("shows dashes for a stopped vm", () => {
    const stopped = { ...running, cpu_percent: null, mem_used_bytes: null,
      mem_total_bytes: null, idle_seconds: null, ports: [] };
    const { getAllByText } = render(StatsBar, { props: { project: stopped } });
    expect(getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });
});
