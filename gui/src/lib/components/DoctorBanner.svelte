<script lang="ts">
  import { onMount } from "svelte";
  import { api, type DoctorReport } from "$lib/tauri";

  let report = $state<DoctorReport | null>(null);
  let open = $state(false);

  onMount(async () => {
    try { report = await api.runDoctor(); } catch { /* ignore; banner just won't show */ }
  });

  const fails = $derived(report?.summary.fails ?? 0);
  const failed = $derived(report?.checks.filter((c) => c.status === "fail") ?? []);
</script>

{#if fails > 0}
  <div class="banner">
    <button class="head" onclick={() => (open = !open)}>
      ⚠ {fails} check{fails === 1 ? "" : "s"} failed — click for details
    </button>
    {#if open}
      <ul class="drawer">
        {#each failed as c}
          <li><strong>{c.name}</strong>{#if c.hint}<div class="hint">{c.hint}</div>{/if}</li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}

<style>
  .banner { background: #fff4d6; border-bottom: 1px solid #e8c878; }
  .head { width: 100%; text-align: left; background: none; border: 0; cursor: pointer;
    padding: 8px 14px; font-size: 12px; color: #8a6d1a; }
  .drawer { margin: 0; padding: 0 14px 10px 30px; font-size: 12px; }
  .drawer li { margin: 4px 0; }
  .hint { color: var(--muted); font-size: 11px; }
</style>
