import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export interface ProjectStatus {
  name: string;
  status: string; // free-form; "Running" | "Stopped" | "Missing" | ...
  uptime_seconds: number | null;
  cpu_percent: number | null;
  mem_used_bytes: number | null;
  mem_total_bytes: number | null;
  primary_repo: string | null;
  branch: string | null;
  idle_seconds: number | null;
  ports: number[];
  profiles: string[];
  repos: string[];
}

export interface ProjectConfig {
  name: string;
  repos: string[];
  primary_repo: string | null;
  profiles: string[];
  shell: string | null;
}

export interface DoctorCheck {
  name: string;
  status: "ok" | "fail";
  detail: string | null;
  hint: string | null;
}
export interface DoctorReport {
  checks: DoctorCheck[];
  summary: { checks: number; fails: number };
}

export type LifecycleAction = "up" | "down" | "update" | "rebuild" | "destroy";
export type JobId = number;

export const api = {
  listProjects: () => invoke<ProjectStatus[]>("list_projects"),
  listConfig: () => invoke<ProjectConfig[]>("list_config"),
  runDoctor: () => invoke<DoctorReport>("run_doctor"),
  addProject: (name: string, repo: string, profiles: string[]) =>
    invoke<void>("add_project", { name, repo, profiles }),
  spawnLifecycle: (project: string, action: LifecycleAction) =>
    invoke<JobId>("spawn_lifecycle", { project, action }),
  cancelJob: (jobId: JobId) => invoke<void>("cancel_job", { jobId }),
  openLogs: () => invoke<void>("open_logs"),
};

export interface LogEvent { line: string; stream: "stdout" | "stderr" }
export interface DoneEvent { exit_code: number; duration_ms: number }

export const events = {
  onProjectsUpdated: (cb: (rows: ProjectStatus[]) => void): Promise<UnlistenFn> =>
    listen<ProjectStatus[]>("projects://updated", (e) => cb(e.payload)),
  onJobLog: (jobId: JobId, cb: (e: LogEvent) => void): Promise<UnlistenFn> =>
    listen<LogEvent>(`job://${jobId}/log`, (e) => cb(e.payload)),
  onJobDone: (jobId: JobId, cb: (e: DoneEvent) => void): Promise<UnlistenFn> =>
    listen<DoneEvent>(`job://${jobId}/done`, (e) => cb(e.payload)),
};
