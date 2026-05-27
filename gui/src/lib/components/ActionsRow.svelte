<script lang="ts">
  import type { JobState } from "$lib/stores";
  import type { LifecycleAction } from "$lib/tauri";

  let { project, activeJob, onRun, onConfirm, onCancel }: {
    project: string;
    activeJob: JobState | null;
    onRun: (action: LifecycleAction) => void;
    onConfirm: (action: "rebuild" | "destroy") => void;
    onCancel: () => void;
  } = $props();
</script>

<div class="actions" data-project={project}>
  {#if activeJob}
    <button class="cancel" onclick={onCancel}>Cancel</button>
  {:else}
    <button onclick={() => onRun("up")}>Up</button>
    <button onclick={() => onRun("down")}>Down</button>
    <button onclick={() => onRun("update")}>Update</button>
    <button onclick={() => onConfirm("rebuild")}>Rebuild</button>
    <button class="danger" onclick={() => onConfirm("destroy")}>Destroy</button>
  {/if}
</div>

<style>
  .actions { display: flex; gap: 6px; }
  button { font-size: 12px; padding: 4px 12px; border: 1px solid var(--border);
    border-radius: 6px; background: var(--btn); cursor: pointer; }
  .danger { color: #c0392b; }
  .cancel { color: #b9770e; }
</style>
