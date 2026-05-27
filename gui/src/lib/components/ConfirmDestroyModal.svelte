<script lang="ts">
  let { project, action, onConfirm, onCancel }: {
    project: string;
    action: "destroy" | "rebuild";
    onConfirm: () => void;
    onCancel: () => void;
  } = $props();

  let typed = $state("");
  const matches = $derived(typed === project);
  const verb = $derived(action === "destroy" ? "Destroy" : "Rebuild");
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onCancel()} />

<div class="backdrop">
  <div class="modal" role="dialog" aria-modal="true" tabindex="-1">
    <h2>{verb} {project}?</h2>
    <p>
      This {action === "destroy" ? "permanently deletes" : "destroys and rebuilds"}
      the VM. Type <strong>{project}</strong> to confirm.
    </p>
    <label>
      <span class="sr">Type the project name</span>
      <input bind:value={typed} placeholder={project} autocomplete="off" />
    </label>
    <div class="row">
      <button onclick={onCancel}>Cancel</button>
      <button class="danger" disabled={!matches} onclick={onConfirm}>{verb}</button>
    </div>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.3);
    display: flex; align-items: center; justify-content: center; }
  .modal { background: var(--panel); border-radius: 10px; padding: 20px;
    width: 360px; box-shadow: 0 10px 40px rgba(0,0,0,.25); }
  h2 { margin: 0 0 8px; font-size: 15px; }
  p { font-size: 12px; color: var(--muted); }
  input { width: 100%; padding: 6px 8px; border: 1px solid var(--border);
    border-radius: 6px; box-sizing: border-box; }
  .row { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
  .danger:not(:disabled) { background: #c0392b; color: #fff; border-color: #c0392b; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
