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
