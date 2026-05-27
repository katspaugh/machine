<script lang="ts">
  import type { ProjectStatus, JobId, LifecycleAction } from "$lib/tauri";
  import { activeJobFor, effectiveStatus, type JobState } from "$lib/stores";
  import { formatDuration } from "$lib/format";
  import StatsBar from "$lib/components/StatsBar.svelte";
  import ActionsRow from "$lib/components/ActionsRow.svelte";
  import LogPane from "$lib/components/LogPane.svelte";

  let { project, jobs, onRun, onConfirm, onCancel }: {
    project: ProjectStatus;
    jobs: Map<JobId, JobState>;
    onRun: (a: LifecycleAction) => void;
    onConfirm: (a: "rebuild" | "destroy") => void;
    onCancel: () => void;
  } = $props();

  const job = $derived(activeJobFor(project.name, jobs));
  // Show the most recent job for this project (active or finished) in the log.
  const shownJob = $derived(
    job ?? [...jobs.values()].filter((j) => j.project === project.name).at(-1) ?? null,
  );
  const status = $derived(effectiveStatus(project, jobs));
</script>

<section class="detail">
  <header>
    <div>
      <div class="title">{project.name}</div>
      <div class="sub">
        <span class="status">{status}</span>
        {#if project.uptime_seconds !== null}· uptime {formatDuration(project.uptime_seconds)}{/if}
        {#each project.profiles as p}<span class="chip">{p}</span>{/each}
      </div>
    </div>
    <ActionsRow project={project.name} activeJob={job}
      {onRun} {onConfirm} {onCancel} />
  </header>

  <StatsBar {project} />

  {#if shownJob}
    <div class="logwrap">
      <div class="logtitle">
        {shownJob.action} {shownJob.project}
        {#if shownJob.done}<span class="exit" class:fail={shownJob.exitCode !== 0}>exit {shownJob.exitCode}</span>{:else}<span class="running">running…</span>{/if}
      </div>
      <LogPane job={shownJob} />
    </div>
  {/if}
</section>

<style>
  .detail { flex: 1; padding: 14px; display: flex; flex-direction: column; gap: 12px; }
  header { display: flex; align-items: flex-start; justify-content: space-between; }
  .title { font-size: 17px; font-weight: 600; }
  .sub { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 6px; }
  .status { font-weight: 500; color: var(--text); }
  .chip { font-size: 10px; background: var(--tile-bg); border-radius: 10px; padding: 1px 8px; }
  .logtitle { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
  .exit { color: #2ecc71; } .exit.fail { color: #e74c3c; }
  .running { color: #f39c12; }
</style>
