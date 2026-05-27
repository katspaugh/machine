import { render, fireEvent } from "@testing-library/svelte";
import { describe, it, expect, vi } from "vitest";
import Sidebar from "./Sidebar.svelte";
import type { ProjectStatus } from "$lib/tauri";

function p(name: string, status: string): ProjectStatus {
  return { name, status, uptime_seconds: null, cpu_percent: null,
    mem_used_bytes: null, mem_total_bytes: null, primary_repo: null,
    branch: null, idle_seconds: null, ports: [], profiles: [], repos: [] };
}

describe("Sidebar", () => {
  it("lists projects and fires onSelect", async () => {
    const onSelect = vi.fn();
    const { getByText } = render(Sidebar, {
      props: { projects: [p("wallet", "Running"), p("blog", "Stopped")],
        jobs: new Map(), selectedName: "wallet", onSelect, onAdd: () => {} },
    });
    await fireEvent.click(getByText("blog"));
    expect(onSelect).toHaveBeenCalledWith("blog");
  });

  it("marks the running project's LED", () => {
    const { container } = render(Sidebar, {
      props: { projects: [p("wallet", "Running")], jobs: new Map(),
        selectedName: "wallet", onSelect: () => {}, onAdd: () => {} },
    });
    expect(container.querySelector(".led.running")).not.toBeNull();
  });

  it("fires onAdd when the add button is clicked", async () => {
    const onAdd = vi.fn();
    const { getByRole } = render(Sidebar, {
      props: { projects: [p("wallet", "Running")], jobs: new Map(),
        selectedName: "wallet", onSelect: () => {}, onAdd },
    });
    await fireEvent.click(getByRole("button", { name: /add project/i }));
    expect(onAdd).toHaveBeenCalled();
  });
});
