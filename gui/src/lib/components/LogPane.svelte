<script lang="ts">
  import { tick } from "svelte";
  import type { JobState } from "$lib/stores";
  import { shouldAutoScroll } from "$lib/scroll";

  let { job }: { job: JobState } = $props();

  let pre: HTMLPreElement | null = $state(null);
  let stuck = $state(true);

  function onScroll() {
    if (pre) stuck = shouldAutoScroll(pre);
  }

  $effect(() => {
    void job.lines.length;
    if (stuck && pre) {
      tick().then(() => { if (pre) pre.scrollTop = pre.scrollHeight; });
    }
  });

  function jumpToBottom() {
    if (pre) { pre.scrollTop = pre.scrollHeight; stuck = true; }
  }
</script>

<div class="logpane">
  <pre bind:this={pre} onscroll={onScroll}>{job.lines.map((l) => l.text).join("\n")}</pre>
  {#if !stuck}
    <button class="jump" onclick={jumpToBottom}>↓ Jump to bottom</button>
  {/if}
</div>

<style>
  .logpane { position: relative; }
  pre {
    background: #1e1e1e; color: #d4d4d4; font: 11px/1.5 ui-monospace, Menlo, monospace;
    padding: 8px; border-radius: 6px; height: 200px; overflow: auto; margin: 0;
    white-space: pre-wrap; word-break: break-word;
  }
  .jump {
    position: absolute; right: 10px; bottom: 10px; font-size: 11px;
    padding: 3px 8px; border-radius: 4px; border: 1px solid #555;
    background: #2a2a2a; color: #ddd; cursor: pointer;
  }
</style>
