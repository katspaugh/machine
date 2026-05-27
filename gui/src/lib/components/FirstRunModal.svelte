<script lang="ts">
  let { profiles, firstRun = true, onSubmit, onSkip }: {
    profiles: string[];
    firstRun?: boolean;
    onSubmit: (p: { name: string; repo: string; profiles: string[] }) => void;
    onSkip: () => void;
  } = $props();

  let name = $state("");
  let repo = $state("");
  let selected = $state<string[]>([]);

  const nameOk = $derived(/^[a-z0-9][a-z0-9-]*$/.test(name));
  const valid = $derived(nameOk && repo.trim().length > 0);

  function toggle(p: string) {
    selected = selected.includes(p) ? selected.filter((x) => x !== p) : [...selected, p];
  }
  function submit() {
    if (valid) onSubmit({ name, repo: repo.trim(), profiles: selected });
  }
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onSkip()} />

<div class="backdrop">
  <div class="modal" role="dialog" aria-modal="true" tabindex="-1">
    <h2>{firstRun ? "Add your first project" : "Add project"}</h2>
    <label>Name
      <input bind:value={name} placeholder="my-project" autocomplete="off" />
    </label>
    {#if name && !nameOk}<p class="err">lowercase letters, digits, hyphen</p>{/if}
    <label>Repo
      <input bind:value={repo} placeholder="git@github.com:you/repo.git" autocomplete="off" />
    </label>
    {#if profiles.length}
      <div class="profiles">
        <span class="lbl">Profiles</span>
        {#each profiles as p}
          <button type="button" class="chip" class:on={selected.includes(p)}
            onclick={() => toggle(p)}>{p}</button>
        {/each}
      </div>
    {/if}
    <div class="row">
      <button onclick={onSkip}>{firstRun ? "Skip" : "Cancel"}</button>
      <button class="primary" disabled={!valid} onclick={submit}>Create</button>
    </div>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.3);
    display: flex; align-items: center; justify-content: center; }
  .modal { background: var(--panel); border-radius: 10px; padding: 20px; width: 380px; }
  h2 { margin: 0 0 12px; font-size: 15px; }
  label { display: block; font-size: 12px; margin-bottom: 8px; }
  input { width: 100%; padding: 6px 8px; margin-top: 3px; border: 1px solid var(--border);
    border-radius: 6px; box-sizing: border-box; }
  .err { color: #c0392b; font-size: 11px; margin: -4px 0 8px; }
  .profiles { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 6px 0; }
  .lbl { font-size: 11px; color: var(--muted); }
  .chip { font-size: 11px; border: 1px solid var(--border); border-radius: 10px;
    padding: 2px 10px; background: none; cursor: pointer; }
  .chip.on { background: var(--selection); border-color: var(--accent); }
  .row { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
  .primary:not(:disabled) { background: var(--accent); color: #fff; border-color: var(--accent); }
</style>
