<script lang="ts">
  import type { ProjectStatus, JobId } from "$lib/tauri";
  import { effectiveStatus, type JobState } from "$lib/stores";

  let { projects, jobs, selectedName, onSelect, onAdd }: {
    projects: ProjectStatus[];
    jobs: Map<JobId, JobState>;
    selectedName: string | null;
    onSelect: (name: string) => void;
    onAdd: () => void;
  } = $props();

  function ledClass(p: ProjectStatus): string {
    const s = effectiveStatus(p, jobs);
    if (s === "Running") return "running";
    if (s === "Provisioning") return "provisioning";
    if (s === "Missing") return "missing";
    return "stopped";
  }
</script>

<nav class="sidebar">
  <div class="section">Projects</div>
  {#each projects as p (p.name)}
    <button class="item" class:selected={p.name === selectedName}
            onclick={() => onSelect(p.name)}>
      <span class="led {ledClass(p)}"></span><span class="name">{p.name}</span>
    </button>
  {/each}
    <button class="add" onclick={onAdd}>+ Add project</button>
</nav>

<style>
  .sidebar { width: 180px; border-right: 1px solid var(--border);
    background: var(--sidebar-bg); padding: 8px 0;
    display: flex; flex-direction: column; }
  .add { margin: auto 8px 4px; padding: 6px 12px; border: 1px dashed var(--border);
    border-radius: 6px; background: none; cursor: pointer; font-size: 12px;
    color: var(--muted); text-align: left; }
  .add:hover { color: var(--text); border-color: var(--accent); }
  .section { padding: 4px 12px; font-size: 9px; text-transform: uppercase;
    letter-spacing: .5px; color: var(--muted); }
  .item { display: flex; align-items: center; gap: 8px; width: 100%;
    padding: 6px 12px; border: 0; background: none; cursor: pointer; text-align: left; }
  .item.selected { background: var(--selection); }
  .name { font-size: 12px; }
  .led { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .led.running { background: #2ecc71; }
  .led.stopped { background: #95a5a6; }
  .led.missing { background: #e74c3c; }
  .led.provisioning { background: #f39c12; }
</style>
