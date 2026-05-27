import { describe, it, expect } from "vitest";
import { activeJobFor, effectiveStatus, type JobState } from "./stores";
import type { ProjectStatus } from "./tauri";

function job(over: Partial<JobState>): JobState {
  return { id: 1, project: "wallet", action: "up", lines: [], done: false,
           exitCode: null, ...over };
}
function proj(over: Partial<ProjectStatus>): ProjectStatus {
  return { name: "wallet", status: "Stopped", uptime_seconds: null,
           cpu_percent: null, mem_used_bytes: null, mem_total_bytes: null,
           primary_repo: null, branch: null, idle_seconds: null,
           ports: [], profiles: [], repos: [], ...over };
}

describe("activeJobFor", () => {
  it("returns the not-done job for the project", () => {
    const jobs = new Map([[1, job({})]]);
    expect(activeJobFor("wallet", jobs)?.id).toBe(1);
  });
  it("ignores done jobs", () => {
    const jobs = new Map([[1, job({ done: true })]]);
    expect(activeJobFor("wallet", jobs)).toBeNull();
  });
  it("ignores other projects", () => {
    const jobs = new Map([[1, job({ project: "blog" })]]);
    expect(activeJobFor("wallet", jobs)).toBeNull();
  });
});

describe("effectiveStatus", () => {
  it("Provisioning when an up job is active", () => {
    const jobs = new Map([[1, job({ action: "up" })]]);
    expect(effectiveStatus(proj({ status: "Stopped" }), jobs)).toBe("Provisioning");
  });
  it("Provisioning when a rebuild job is active", () => {
    const jobs = new Map([[1, job({ action: "rebuild" })]]);
    expect(effectiveStatus(proj({ status: "Running" }), jobs)).toBe("Provisioning");
  });
  it("raw status for a down job", () => {
    const jobs = new Map([[1, job({ action: "down" })]]);
    expect(effectiveStatus(proj({ status: "Running" }), jobs)).toBe("Running");
  });
  it("raw status when no job", () => {
    expect(effectiveStatus(proj({ status: "Running" }), new Map())).toBe("Running");
  });
});
