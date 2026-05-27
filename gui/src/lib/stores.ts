import { writable, derived } from "svelte/store";
import type { ProjectStatus, JobId } from "./tauri";

export interface JobState {
  id: JobId;
  project: string;
  action: string;
  lines: { text: string; stream: "stdout" | "stderr" }[];
  done: boolean;
  exitCode: number | null;
}

export const projects = writable<ProjectStatus[]>([]);
export const jobs = writable<Map<JobId, JobState>>(new Map());
export const selectedName = writable<string | null>(null);

export const selectedProject = derived(
  [projects, selectedName],
  ([$projects, $selectedName]) =>
    $projects.find((p) => p.name === $selectedName) ?? null,
);

/** The active (not-done) job for a project, or null. */
export function activeJobFor(
  project: string,
  jobs: Map<JobId, JobState>,
): JobState | null {
  for (const j of jobs.values()) {
    if (j.project === project && !j.done) return j;
  }
  return null;
}

/** Effective status: a project mid-up/rebuild reads as "Provisioning",
 *  since the CLI itself never emits that status. */
export function effectiveStatus(
  project: { name: string; status: string },
  jobs: Map<JobId, JobState>,
): string {
  const j = activeJobFor(project.name, jobs);
  if (j && (j.action === "up" || j.action === "rebuild")) return "Provisioning";
  return project.status;
}
