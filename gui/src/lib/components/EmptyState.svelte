<script lang="ts">
  import { api } from "$lib/tauri";
  let { onAdd }: { onAdd: () => void } = $props();
</script>

<div class="empty">
  <h2>No projects yet</h2>
  <p>Add one to get started, or edit <code>projects.toml</code> directly.</p>
  <div class="row">
    <button class="primary" onclick={onAdd}>Add project</button>
    <button onclick={() => api.openLogs()}>Reveal config in Finder</button>
    <a href="https://runmachine.dev/" target="_blank" rel="noreferrer">Docs</a>
  </div>
</div>

<style>
  .empty { flex: 1; display: flex; flex-direction: column; align-items: center;
    justify-content: center; gap: 8px; color: var(--muted); }
  h2 { color: var(--text); margin: 0; }
  .row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
  .primary { background: var(--accent); color: #fff; border: 0; border-radius: 6px;
    padding: 6px 14px; cursor: pointer; }
</style>
