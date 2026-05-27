<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { api, events, type LifecycleAction, type JobId } from "$lib/tauri";
  import { projects, selectedName, selectedProject, jobs } from "$lib/stores";
  import type { JobState } from "$lib/stores";

  let activeJob = $state<JobState | null>(null);
  let error = $state<string | null>(null);
  // An async onMount can't return the unlisten as a cleanup (Svelte expects a
  // sync cleanup), so hold it and tear down in onDestroy.
  let unlistenProjects: (() => void) | null = null;

  onMount(async () => {
    try {
      $projects = await api.listProjects();
      if (!$selectedName && $projects.length) $selectedName = $projects[0].name;
    } catch (e) {
      error = String(e);
    }
    unlistenProjects = await events.onProjectsUpdated((rows) => {
      $projects = rows;
      // Keep selection valid; fall back to the first project if it vanished.
      if ($selectedName && !rows.some((r) => r.name === $selectedName)) {
        $selectedName = rows.length ? rows[0].name : null;
      }
    });
  });

  onDestroy(() => unlistenProjects?.());

  async function run(action: LifecycleAction) {
    const p = $selectedProject;
    if (!p) return;
    error = null;
    try {
      const id: JobId = await api.spawnLifecycle(p.name, action);
      const job: JobState = {
        id, project: p.name, action, lines: [], done: false, exitCode: null,
      };
      activeJob = job;
      $jobs = new Map($jobs).set(id, job);
      // NOTE: these per-job listeners are intentionally not unlistened in this
      // foundation slice — proper lifecycle/cleanup arrives with the LogPane
      // component in plan 2b.
      await events.onJobLog(id, (e) => {
        job.lines = [...job.lines, { text: e.line, stream: e.stream }];
        activeJob = { ...job };
      });
      await events.onJobDone(id, (e) => {
        job.done = true;
        job.exitCode = e.exit_code;
        activeJob = { ...job };
      });
    } catch (e) {
      error = String(e);
    }
  }
</script>

<main>
  <h1>machine</h1>
  {#if error}<p style="color:#c0392b">{error}</p>{/if}

  <div style="display:flex; gap:1rem;">
    <!-- sidebar -->
    <ul style="list-style:none; padding:0; min-width:160px;">
      {#each $projects as p (p.name)}
        <li>
          <button
            onclick={() => ($selectedName = p.name)}
            style="font-weight:{$selectedName === p.name ? 'bold' : 'normal'}">
            {p.status === "Running" ? "●" : p.status === "Missing" ? "○" : "◐"} {p.name}
          </button>
        </li>
      {/each}
      {#if $projects.length === 0}<li>(no projects)</li>{/if}
    </ul>

    <!-- detail -->
    <section style="flex:1">
      {#if $selectedProject}
        {@const p = $selectedProject}
        <h2>{p.name} — {p.status}</h2>
        <p>
          profiles: {p.profiles.join(", ") || "—"} ·
          repo: {p.primary_repo ?? "—"} ·
          cpu: {p.cpu_percent ?? "—"}% ·
          mem: {p.mem_used_bytes ?? "—"}/{p.mem_total_bytes ?? "—"} ·
          ports: {p.ports.join(", ") || "—"}
        </p>
        <div style="display:flex; gap:.5rem;">
          <button onclick={() => run("up")}>Up</button>
          <button onclick={() => run("down")}>Down</button>
          <button onclick={() => run("update")}>Update</button>
          <button onclick={() => run("rebuild")}>Rebuild</button>
          <button onclick={() => run("destroy")}>Destroy</button>
          <button onclick={() => api.openLogs()}>Open logs</button>
        </div>
      {:else}
        <p>Select a project.</p>
      {/if}

      {#if activeJob}
        <h3>{activeJob.action} {activeJob.project}
          {activeJob.done ? `(exit ${activeJob.exitCode})` : "(running…)"}</h3>
        <pre style="background:#1e1e1e; color:#ddd; padding:.5rem; height:200px; overflow:auto;">{activeJob.lines.map((l) => l.text).join("\n")}</pre>
      {/if}
    </section>
  </div>
</main>
