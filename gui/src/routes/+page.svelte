<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { api, events, type LifecycleAction, type JobId } from "$lib/tauri";
  import { projects, selectedName, selectedProject, jobs, activeJobFor,
    type JobState } from "$lib/stores";
  import Sidebar from "$lib/components/Sidebar.svelte";
  import DetailPanel from "$lib/components/DetailPanel.svelte";
  import EmptyState from "$lib/components/EmptyState.svelte";
  import FirstRunModal from "$lib/components/FirstRunModal.svelte";
  import ConfirmDestroyModal from "$lib/components/ConfirmDestroyModal.svelte";
  import DoctorBanner from "$lib/components/DoctorBanner.svelte";

  let confirming = $state<{ project: string; action: "rebuild" | "destroy" } | null>(null);
  let showAddModal = $state(false);
  let availableProfiles = $state<string[]>([]);
  let error = $state<string | null>(null);
  let unlistenProjects: (() => void) | null = null;

  onMount(async () => {
    try {
      $projects = await api.listProjects();
      if (!$selectedName && $projects.length) $selectedName = $projects[0].name;
      if ($projects.length === 0) showAddModal = true;
      availableProfiles = await api.listProfiles();
    } catch (e) { error = String(e); }

    unlistenProjects = await events.onProjectsUpdated((rows) => {
      $projects = rows;
      if ($selectedName && !rows.some((r) => r.name === $selectedName)) {
        $selectedName = rows.length ? rows[0].name : null;
      }
    });
  });

  onDestroy(() => unlistenProjects?.());

  async function startJob(project: string, action: LifecycleAction) {
    error = null;
    try {
      const id: JobId = await api.spawnLifecycle(project, action);
      const job: JobState = { id, project, action, lines: [], done: false, exitCode: null };
      $jobs = new Map($jobs).set(id, job);
      await events.onJobLog(id, (e) => {
        job.lines = [...job.lines, { text: e.line, stream: e.stream }];
        $jobs = new Map($jobs).set(id, { ...job });
      });
      await events.onJobDone(id, (e) => {
        job.done = true; job.exitCode = e.exit_code;
        $jobs = new Map($jobs).set(id, { ...job });
      });
    } catch (e) { error = String(e); }
  }

  function onRun(action: LifecycleAction) {
    if ($selectedProject) startJob($selectedProject.name, action);
  }
  function onConfirm(action: "rebuild" | "destroy") {
    if ($selectedProject) confirming = { project: $selectedProject.name, action };
  }
  function onCancel() {
    const p = $selectedProject;
    if (!p) return;
    const j = activeJobFor(p.name, $jobs);
    if (j) api.cancelJob(j.id);
  }
  function confirmYes() {
    if (confirming) { startJob(confirming.project, confirming.action); confirming = null; }
  }
  async function firstRunSubmit(p: { name: string; repo: string; profiles: string[] }) {
    error = null;
    try {
      await api.addProject(p.name, p.repo, p.profiles);
      $projects = await api.listProjects();
      $selectedName = p.name;
      showAddModal = false;
    } catch (e) { error = String(e); }
  }
</script>

<DoctorBanner />
{#if error}<div class="errbar">{error}</div>{/if}

<div class="layout">
  <Sidebar projects={$projects} jobs={$jobs} selectedName={$selectedName}
    onSelect={(n) => ($selectedName = n)} onAdd={() => (showAddModal = true)} />
  {#if $selectedProject}
    <DetailPanel project={$selectedProject} jobs={$jobs}
      {onRun} {onConfirm} {onCancel} />
  {:else}
    <EmptyState onAdd={() => (showAddModal = true)} />
  {/if}
</div>

{#if confirming}
  <ConfirmDestroyModal project={confirming.project} action={confirming.action}
    onConfirm={confirmYes} onCancel={() => (confirming = null)} />
{/if}
{#if showAddModal}
  <FirstRunModal profiles={availableProfiles} firstRun={$projects.length === 0}
    onSubmit={firstRunSubmit} onSkip={() => (showAddModal = false)} />
{/if}

<style>
  .layout { display: flex; height: 100vh; }
  .errbar { background: #fdecea; color: #c0392b; padding: 6px 14px; font-size: 12px; }
</style>
