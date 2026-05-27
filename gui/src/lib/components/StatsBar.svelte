<script lang="ts">
  import type { ProjectStatus } from "$lib/tauri";
  import { formatPercent, formatMem, formatDuration } from "$lib/format";

  let { project }: { project: ProjectStatus } = $props();

  const ports = $derived(project.ports.length ? project.ports.join(", ") : "—");
</script>

<div class="stats">
  <div class="tile"><div class="label">CPU</div><div class="value">{formatPercent(project.cpu_percent)}</div></div>
  <div class="tile"><div class="label">Mem</div><div class="value">{formatMem(project.mem_used_bytes, project.mem_total_bytes)}</div></div>
  <div class="tile"><div class="label">Idle</div><div class="value">{formatDuration(project.idle_seconds)}</div></div>
  <div class="tile"><div class="label">Ports</div><div class="value">{ports}</div></div>
</div>

<style>
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  .tile { background: var(--tile-bg); border-radius: 6px; padding: 8px 10px; }
  .label { font-size: 10px; text-transform: uppercase; letter-spacing: .4px; color: var(--muted); }
  .value { font-size: 13px; font-weight: 500; }
</style>
