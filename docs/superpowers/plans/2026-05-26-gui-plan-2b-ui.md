# Plan 2b: GUI Component UI (components, modals, first-run, doctor banner, styling) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn plan 2a's bare wired slice into the real v1 UI: extract `Sidebar`/`DetailPanel`/`StatsBar`/`ActionsRow`/`LogPane`, add the `ConfirmDestroyModal` and `FirstRunModal`, the empty/first-run flow, the `DoctorBanner`, and the macOS styling pass. Numbers get formatted (bytes/seconds/percent), a project with an active `up`/`rebuild` job shows as **Provisioning**, the log pane scroll-locks and auto-collapses on success, and destructive actions require typing the project name.

**Architecture:** Same Tauri backend from 2a — this plan is almost entirely frontend, plus two small read-only Rust commands (`init_config` is *not* added; `list_profiles` is, to populate the first-run dropdown). The `App.svelte` slice is decomposed into focused components that read the shared stores; cross-cutting derived state (effective status, the active job for a project) moves into `lib/stores.ts` and `lib/format.ts` so components stay thin.

**Tech Stack:** Svelte 5 (runes) + TypeScript + plain CSS, Vitest + `@testing-library/svelte` for component/unit tests. Rust additions use the same `cli`/command patterns from 2a.

---

## Prerequisites

- **Plan 2a must be merged** — this plan refactors `gui/src/routes/+page.svelte` and reuses `$lib/tauri.ts`, `$lib/stores.ts`, and the Rust commands.
- Same toolchain caveats as 2a: execute on macOS (or Linux-with-WebKitGTK for the non-macOS-specific parts). Commits are signed; the signing agent is intermittently flaky — retry on `communication with agent failed`, never `--no-gpg-sign`.
- **Svelte 5 + Vitest API drift:** component-test setup (`@testing-library/svelte`, `vitest`, `jsdom`) and Svelte 5 runes are stable but verify against installed versions; each component task has a "run the test, confirm it passes" step that surfaces any mismatch.

## SvelteKit adaptation (the 2a scaffold is SvelteKit, not plain Vite+Svelte)

Plan 2a's `create-tauri-app` generated a **SvelteKit** app (adapter-static, SPA mode, `ssr = false`), not the plain Vite+Svelte layout this plan was originally drafted against. Apply these substitutions **throughout every task below**:

1. **Components live in `gui/src/lib/components/`** (the original draft used a bare `src/components/` dir — ignore that). SvelteKit's `$lib` alias resolves to `gui/src/lib`, so `$lib/components/Foo.svelte` is the import path.
2. **All imports use the `$lib` alias**, not relative `../lib/` or `./Sibling.svelte`. Concretely, in every code block below:
   - `from "../lib/tauri"` → `from "$lib/tauri"`
   - `from "../lib/stores"` → `from "$lib/stores"`
   - `from "../lib/format"` → `from "$lib/format"`
   - `from "./StatsBar.svelte"` (and any sibling component) → `from "$lib/components/StatsBar.svelte"`
   - test files import the component under test by **relative** path (`./Foo.svelte`) since the test sits next to it in `lib/components/`, but import `$lib/...` for everything else.
3. **The "App.svelte" composition (Task 12) is `gui/src/routes/+page.svelte`.** 2a already wrote the slice there; Task 12 rewrites that file. There is **no `gui/src/App.svelte`** and **no `gui/src/main.ts`**.
4. **Global CSS (Task 13)** is wired via a new `gui/src/routes/+layout.svelte` importing `gui/src/app.css` — not a `main.ts` import.
5. **Async `onMount` cleanup**: SvelteKit/Svelte expects a *synchronous* cleanup return from `onMount`. 2a's `+page.svelte` holds the unlisten in a variable and tears down in `onDestroy` — follow that pattern (do NOT `return un;` from an async `onMount`).
6. **Vitest needs the `$lib` alias** resolved (Task 1 sets this up).

## Decisions carried into this plan

- **No `machine init` call.** The spec's first-run text said "GUI calls `machine init` then opens the modal," but plan 1's `config add-project` already creates `projects.toml` if absent. So the first-run modal calls `add_project` directly — simpler, one fewer command, and the GUI is now the editor (the commented-example file matters less). The empty-state pane still offers "Reveal in Finder" / "Docs".
- **Effective status = Provisioning.** Plan 1's `ps --json` never emits `Provisioning` (carry-forward note in the spec). The UI derives it: a project with an active, not-done `up` or `rebuild` job renders as `Provisioning` regardless of the CLI's reported status.
- **`list_profiles` command added.** The first-run profile dropdown needs the set of available profiles (`profiles/*.toml`). The CLI has no JSON command for this, so 2b adds a small read-only Rust command that lists the profile-file basenames (directory listing, not config parsing).

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `gui/src-tauri/src/cli.rs` | Modify | Add `profiles_dir()` resolver. |
| `gui/src-tauri/src/lib.rs` | Modify | Add `list_profiles` command + register it. |
| `gui/vitest.config.ts` | Create | Vitest + jsdom + svelte plugin config. |
| `gui/src/lib/format.ts` | Create | `formatBytes`, `formatDuration`, `formatPercent`, `formatMem`. |
| `gui/src/lib/stores.ts` | Modify | Add `activeJobFor(project)` + `effectiveStatus(project, jobs)` derivations and the job-event ingestion helpers. |
| `gui/src/lib/tauri.ts` | Modify | Add `listProfiles()`. |
| `gui/src/lib/components/Sidebar.svelte` | Create | Project list, status LED, selection. |
| `gui/src/lib/components/StatsBar.svelte` | Create | CPU/mem/idle/ports tiles. |
| `gui/src/lib/components/ActionsRow.svelte` | Create | Lifecycle buttons; collapses to Cancel while running; rebuild/destroy gate on the modal. |
| `gui/src/lib/components/LogPane.svelte` | Create | Streaming log, scroll-lock, jump-to-bottom, auto-collapse on success. |
| `gui/src/lib/components/DetailPanel.svelte` | Create | Header + StatsBar + ActionsRow + LogPane. |
| `gui/src/lib/components/ConfirmDestroyModal.svelte` | Create | Type-project-name-to-confirm. |
| `gui/src/lib/components/FirstRunModal.svelte` | Create | name/repo/profile form → `add_project`. |
| `gui/src/lib/components/EmptyState.svelte` | Create | Shown when there are no projects. |
| `gui/src/lib/components/DoctorBanner.svelte` | Create | Yellow banner + expandable drawer from `run_doctor`. |
| `gui/src/app.css` | Create | macOS styling: system font, hairline borders, LED colors, buttons. |
| `gui/src/routes/+layout.svelte` | Create | Imports `app.css` (SvelteKit global-style entry). |
| `gui/src/routes/+page.svelte` | Modify | Compose the components; replace the inline 2a slice. |

(Component test files `*.test.ts` sit next to each component in `gui/src/lib/components/`.)

---

## Task 1: Vitest + Testing Library setup

**Files:** Create `gui/vitest.config.ts`; modify `gui/package.json`.

- [ ] **Step 1.1: Install dev deps**

```bash
cd gui
pnpm add -D vitest @testing-library/svelte @testing-library/jest-dom jsdom @vitest/ui
```

- [ ] **Step 1.2: Create `gui/vitest.config.ts`**

SvelteKit tests need the `$lib` alias resolved (vitest doesn't know SvelteKit's aliases on its own). Map it to `src/lib`:

```ts
import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [svelte({ hot: false })],
  resolve: {
    alias: {
      $lib: fileURLToPath(new URL("./src/lib", import.meta.url)),
    },
    // Use the browser build of svelte in jsdom tests so $state/$effect work.
    conditions: ["browser"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
```

> **Verify (Step 1.5):** the `resolve.conditions: ["browser"]` line is what lets Testing Library mount Svelte 5 components under jsdom; if the installed `@testing-library/svelte` + vitest combo already handles this (some versions do via the svelte plugin), it's harmless. If component mounting fails with a "lifecycle_outside_component" or similar runes error, that condition (or `@testing-library/svelte`'s vitest plugin) is the fix point.

- [ ] **Step 1.3: Create `gui/src/test-setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 1.4: Add a test script** — in `gui/package.json` `"scripts"`, add:

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 1.5: Smoke the harness** — create `gui/src/lib/format.test.ts` with a trivial passing test, run it, delete it (Task 2 adds the real one):

```bash
printf 'import { it, expect } from "vitest";\nit("harness", () => expect(1).toBe(1));\n' > src/lib/_harness.test.ts
pnpm test
rm src/lib/_harness.test.ts
```

Expected: 1 test passes (proves vitest + svelte plugin load).

- [ ] **Step 1.6: Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/package.json gui/pnpm-lock.yaml gui/vitest.config.ts gui/src/test-setup.ts
git commit -m "$(cat <<'EOF'
Add Vitest + Testing Library to the gui

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Formatting helpers

**Files:** Create `gui/src/lib/format.ts`, `gui/src/lib/format.test.ts`.

Pure functions that turn the raw contract numbers into display strings. Tested in isolation.

- [ ] **Step 2.1: Write the failing tests** — `gui/src/lib/format.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { formatBytes, formatDuration, formatPercent, formatMem } from "./format";

describe("formatBytes", () => {
  it("formats GB", () => expect(formatBytes(1_932_735_283)).toBe("1.8 GB"));
  it("formats MB", () => expect(formatBytes(52_428_800)).toBe("50 MB"));
  it("null → dash", () => expect(formatBytes(null)).toBe("—"));
});

describe("formatDuration", () => {
  it("seconds", () => expect(formatDuration(45)).toBe("45s"));
  it("minutes", () => expect(formatDuration(125)).toBe("2m"));
  it("hours+minutes", () => expect(formatDuration(8040)).toBe("2h 14m"));
  it("days", () => expect(formatDuration(180000)).toBe("2d 2h"));
  it("null → dash", () => expect(formatDuration(null)).toBe("—"));
});

describe("formatPercent", () => {
  it("rounds", () => expect(formatPercent(2.1)).toBe("2%"));
  it("null → dash", () => expect(formatPercent(null)).toBe("—"));
});

describe("formatMem", () => {
  it("used / total", () =>
    expect(formatMem(1_932_735_283, 8_589_934_592)).toBe("1.8 / 8 GB"));
  it("null → dash", () => expect(formatMem(null, null)).toBe("—"));
});
```

- [ ] **Step 2.2: Run, confirm fail** (`cd gui && pnpm test` → module-not-found / fn-undefined).

- [ ] **Step 2.3: Implement `gui/src/lib/format.ts`**

```ts
const DASH = "—";

export function formatBytes(n: number | null): string {
  if (n === null) return DASH;
  const gb = n / 1_073_741_824;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = n / 1_048_576;
  return `${Math.round(mb)} MB`;
}

export function formatDuration(secs: number | null): string {
  if (secs === null) return DASH;
  if (secs < 60) return `${Math.floor(secs)}s`;
  const m = Math.floor(secs / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

export function formatPercent(p: number | null): string {
  if (p === null) return DASH;
  return `${Math.round(p)}%`;
}

export function formatMem(used: number | null, total: number | null): string {
  if (used === null || total === null) return DASH;
  const u = used / 1_073_741_824;
  const t = total / 1_073_741_824;
  return `${u.toFixed(1)} / ${Math.round(t)} GB`;
}
```

- [ ] **Step 2.4: Run, confirm pass** (`pnpm test`).

- [ ] **Step 2.5: Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/lib/format.ts gui/src/lib/format.test.ts
git commit -m "$(cat <<'EOF'
Add display formatters for the raw contract numbers

formatBytes/formatDuration/formatPercent/formatMem turn ps --json's
raw seconds/bytes/percent into human strings; null → em-dash.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Store derivations — active job + effective status

**Files:** Modify `gui/src/lib/stores.ts`; create `gui/src/lib/stores.test.ts`.

Add pure helpers: `activeJobFor(project, jobs)` and `effectiveStatus(project, jobs)` (Provisioning derivation). Keep them pure functions (not stores) so they're trivially testable and callable from components with current store values.

- [ ] **Step 3.1: Write the failing tests** — `gui/src/lib/stores.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { activeJobFor, effectiveStatus, type JobState } from "./stores";
import type { ProjectStatus } from "./tauri";

function job(over: Partial<JobState>): JobState {
  return { id: 1, project: "wallet", action: "up", lines: [], done: false,
           exitCode: null, ...over };
}
function proj(over: Partial<ProjectStatus>): ProjectStatus {
  return { name: "wallet", status: "Stopped", uptime_seconds: null,
           cpu_percent: null, mem_used_bytes: null, mem_total_bytes: null,
           primary_repo: null, branch: null, idle_seconds: null,
           ports: [], profiles: [], repos: [], ...over };
}

describe("activeJobFor", () => {
  it("returns the not-done job for the project", () => {
    const jobs = new Map([[1, job({})]]);
    expect(activeJobFor("wallet", jobs)?.id).toBe(1);
  });
  it("ignores done jobs", () => {
    const jobs = new Map([[1, job({ done: true })]]);
    expect(activeJobFor("wallet", jobs)).toBeNull();
  });
  it("ignores other projects", () => {
    const jobs = new Map([[1, job({ project: "blog" })]]);
    expect(activeJobFor("wallet", jobs)).toBeNull();
  });
});

describe("effectiveStatus", () => {
  it("Provisioning when an up job is active", () => {
    const jobs = new Map([[1, job({ action: "up" })]]);
    expect(effectiveStatus(proj({ status: "Stopped" }), jobs)).toBe("Provisioning");
  });
  it("Provisioning when a rebuild job is active", () => {
    const jobs = new Map([[1, job({ action: "rebuild" })]]);
    expect(effectiveStatus(proj({ status: "Running" }), jobs)).toBe("Provisioning");
  });
  it("raw status for a down job", () => {
    const jobs = new Map([[1, job({ action: "down" })]]);
    expect(effectiveStatus(proj({ status: "Running" }), jobs)).toBe("Running");
  });
  it("raw status when no job", () => {
    expect(effectiveStatus(proj({ status: "Running" }), new Map())).toBe("Running");
  });
});
```

- [ ] **Step 3.2: Run, confirm fail.**

- [ ] **Step 3.3: Add to `gui/src/lib/stores.ts`** (append; keep the existing exports from 2a):

```ts
import type { JobId } from "./tauri";

// (JobState, projects, jobs, selectedName, selectedProject already exist from 2a)

/** The active (not-done) job for a project, or null. */
export function activeJobFor(
  project: string,
  jobs: Map<JobId, JobState>,
): JobState | null {
  for (const j of jobs.values()) {
    if (j.project === project && !j.done) return j;
  }
  return null;
}

/** Effective status: a project mid-up/rebuild reads as "Provisioning",
 *  since the CLI itself never emits that status. */
export function effectiveStatus(
  project: { name: string; status: string },
  jobs: Map<JobId, JobState>,
): string {
  const j = activeJobFor(project.name, jobs);
  if (j && (j.action === "up" || j.action === "rebuild")) return "Provisioning";
  return project.status;
}
```

- [ ] **Step 3.4: Run, confirm pass.**

- [ ] **Step 3.5: Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/lib/stores.ts gui/src/lib/stores.test.ts
git commit -m "$(cat <<'EOF'
Add activeJobFor + effectiveStatus store helpers

effectiveStatus derives Provisioning from an active up/rebuild job,
since ps --json never emits it (plan-1 carry-forward).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `StatsBar.svelte`

**Files:** Create `gui/src/lib/components/StatsBar.svelte`, `gui/src/lib/components/StatsBar.test.ts`.

Four tiles (CPU / Mem / Idle / Ports) using the Task 2 formatters. Pure presentational — takes a `ProjectStatus` prop.

- [ ] **Step 4.1: Write the failing test** — `StatsBar.test.ts`:

```ts
import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import StatsBar from "./StatsBar.svelte";
import type { ProjectStatus } from "../lib/tauri";

const running: ProjectStatus = {
  name: "wallet", status: "Running", uptime_seconds: 8040, cpu_percent: 2.1,
  mem_used_bytes: 1_932_735_283, mem_total_bytes: 8_589_934_592,
  primary_repo: "wallet", branch: "main", idle_seconds: 180,
  ports: [3000, 5173], profiles: ["cypress"], repos: [],
};

describe("StatsBar", () => {
  it("renders formatted stats", () => {
    const { getByText } = render(StatsBar, { props: { project: running } });
    expect(getByText("2%")).toBeInTheDocument();
    expect(getByText("1.8 / 8 GB")).toBeInTheDocument();
    expect(getByText("3m")).toBeInTheDocument();         // idle 180s
    expect(getByText("3000, 5173")).toBeInTheDocument();
  });

  it("shows dashes for a stopped vm", () => {
    const stopped = { ...running, cpu_percent: null, mem_used_bytes: null,
      mem_total_bytes: null, idle_seconds: null, ports: [] };
    const { getAllByText } = render(StatsBar, { props: { project: stopped } });
    expect(getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });
});
```

- [ ] **Step 4.2: Run, confirm fail.**

- [ ] **Step 4.3: Implement `StatsBar.svelte`**

```svelte
<script lang="ts">
  import type { ProjectStatus } from "../lib/tauri";
  import { formatPercent, formatMem, formatDuration } from "../lib/format";

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
```

- [ ] **Step 4.4: Run, confirm pass.**

- [ ] **Step 4.5: Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/lib/components/StatsBar.svelte gui/src/lib/components/StatsBar.test.ts
git commit -m "$(cat <<'EOF'
Add StatsBar component (CPU/mem/idle/ports tiles)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `LogPane.svelte`

**Files:** Create `gui/src/lib/components/LogPane.svelte`, `gui/src/lib/components/LogPane.test.ts`.

Renders a `JobState`'s lines. Scroll-locks to bottom unless the user scrolled up (then shows a "Jump to bottom" button). The scroll-lock decision is the testable logic — extract it as a pure helper so the test doesn't fight jsdom's layout.

- [ ] **Step 5.1: Write the failing test** — `LogPane.test.ts`:

```ts
import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import LogPane, { shouldAutoScroll } from "./LogPane.svelte";
import type { JobState } from "../lib/stores";

const job: JobState = {
  id: 1, project: "wallet", action: "up", done: false, exitCode: null,
  lines: [{ text: "step 1", stream: "stdout" }, { text: "step 2", stream: "stdout" }],
};

describe("shouldAutoScroll", () => {
  it("true when near the bottom", () =>
    expect(shouldAutoScroll({ scrollTop: 880, scrollHeight: 1000, clientHeight: 120 })).toBe(true));
  it("false when scrolled up", () =>
    expect(shouldAutoScroll({ scrollTop: 200, scrollHeight: 1000, clientHeight: 120 })).toBe(false));
});

describe("LogPane", () => {
  it("renders log lines", () => {
    const { getByText } = render(LogPane, { props: { job } });
    expect(getByText("step 1")).toBeInTheDocument();
    expect(getByText("step 2")).toBeInTheDocument();
  });
});
```

> Note: exporting a function from a `.svelte` `<script module>` block is the Svelte 5 way to expose `shouldAutoScroll` for unit testing. Verify the import works; if the installed Svelte rejects named exports from components, move `shouldAutoScroll` to `lib/format.ts` (or a new `lib/scroll.ts`) and import it in both the component and the test.

- [ ] **Step 5.2: Run, confirm fail.**

- [ ] **Step 5.3: Implement `LogPane.svelte`**

```svelte
<script module lang="ts">
  /** Auto-scroll if the viewport is within 40px of the bottom. */
  export function shouldAutoScroll(m: {
    scrollTop: number; scrollHeight: number; clientHeight: number;
  }): boolean {
    return m.scrollHeight - (m.scrollTop + m.clientHeight) < 40;
  }
</script>

<script lang="ts">
  import { tick } from "svelte";
  import type { JobState } from "../lib/stores";

  let { job }: { job: JobState } = $props();

  let pre: HTMLPreElement | null = $state(null);
  let stuck = $state(true); // are we pinned to the bottom?

  function onScroll() {
    if (pre) stuck = shouldAutoScroll(pre);
  }

  // After each line update, if we were stuck to bottom, stay there.
  $effect(() => {
    void job.lines.length; // dependency
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
```

- [ ] **Step 5.4: Run, confirm pass.**

- [ ] **Step 5.5: Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/lib/components/LogPane.svelte gui/src/lib/components/LogPane.test.ts
git commit -m "$(cat <<'EOF'
Add LogPane with scroll-lock + jump-to-bottom

Pins to the bottom while streaming unless the user scrolls up; the
scroll decision is a pure exported helper so it's unit-testable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `ConfirmDestroyModal.svelte`

**Files:** Create `gui/src/lib/components/ConfirmDestroyModal.svelte`, `.test.ts`.

Type-the-name-to-confirm. Confirm button disabled until the typed text equals the project name. Emits `confirm` / `cancel` via callback props (Svelte 5 uses callback props, not `createEventDispatcher`).

- [ ] **Step 6.1: Write the failing test**

```ts
import { render, fireEvent } from "@testing-library/svelte";
import { describe, it, expect, vi } from "vitest";
import ConfirmDestroyModal from "./ConfirmDestroyModal.svelte";

describe("ConfirmDestroyModal", () => {
  it("disables confirm until the name matches", async () => {
    const onConfirm = vi.fn();
    const { getByRole, getByLabelText } = render(ConfirmDestroyModal, {
      props: { project: "wallet", action: "destroy", onConfirm, onCancel: () => {} },
    });
    const btn = getByRole("button", { name: /destroy/i });
    expect(btn).toBeDisabled();
    await fireEvent.input(getByLabelText(/type the project name/i),
      { target: { value: "wallet" } });
    expect(btn).not.toBeDisabled();
    await fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("does not confirm on a wrong name", async () => {
    const onConfirm = vi.fn();
    const { getByRole, getByLabelText } = render(ConfirmDestroyModal, {
      props: { project: "wallet", action: "rebuild", onConfirm, onCancel: () => {} },
    });
    await fireEvent.input(getByLabelText(/type the project name/i),
      { target: { value: "wrong" } });
    expect(getByRole("button", { name: /rebuild/i })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 6.2: Run, confirm fail.**

- [ ] **Step 6.3: Implement `ConfirmDestroyModal.svelte`**

```svelte
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

<div class="backdrop" onclick={onCancel} role="presentation">
  <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
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
```

> The `<label>` wraps the input and the visually-hidden `.sr` span carries the accessible name "Type the project name" that the test queries via `getByLabelText`. Verify `getByLabelText(/type the project name/i)` resolves; if `@testing-library` doesn't associate the wrapped label, switch to an explicit `for`/`id` pairing.

- [ ] **Step 6.4: Run, confirm pass. Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/lib/components/ConfirmDestroyModal.svelte gui/src/lib/components/ConfirmDestroyModal.test.ts
git commit -m "$(cat <<'EOF'
Add ConfirmDestroyModal (type-name-to-confirm)

Confirm button stays disabled until the typed text equals the project
name; gates destroy and rebuild.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `ActionsRow.svelte`

**Files:** Create `gui/src/lib/components/ActionsRow.svelte`, `.test.ts`.

Lifecycle buttons. When a job is active for the project, the row collapses to a single **Cancel**. **Rebuild**/**Destroy** don't fire immediately — they request confirmation via a callback the parent wires to the modal. Up/Down/Update fire directly.

- [ ] **Step 7.1: Write the failing test**

```ts
import { render, fireEvent } from "@testing-library/svelte";
import { describe, it, expect, vi } from "vitest";
import ActionsRow from "./ActionsRow.svelte";

const base = {
  project: "wallet",
  onRun: vi.fn(),        // (action) => void  for up/down/update
  onConfirm: vi.fn(),    // (action) => void  for rebuild/destroy
  onCancel: vi.fn(),     // () => void
};

describe("ActionsRow", () => {
  it("fires onRun for up directly", async () => {
    const onRun = vi.fn();
    const { getByRole } = render(ActionsRow, { props: { ...base, onRun, activeJob: null } });
    await fireEvent.click(getByRole("button", { name: /^up$/i }));
    expect(onRun).toHaveBeenCalledWith("up");
  });

  it("requests confirmation for destroy", async () => {
    const onConfirm = vi.fn();
    const { getByRole } = render(ActionsRow, { props: { ...base, onConfirm, activeJob: null } });
    await fireEvent.click(getByRole("button", { name: /^destroy$/i }));
    expect(onConfirm).toHaveBeenCalledWith("destroy");
  });

  it("collapses to Cancel while a job runs", () => {
    const { getByRole, queryByRole } = render(ActionsRow, {
      props: { ...base, activeJob: { id: 1, project: "wallet", action: "up",
        lines: [], done: false, exitCode: null } },
    });
    expect(getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    expect(queryByRole("button", { name: /^up$/i })).toBeNull();
  });
});
```

- [ ] **Step 7.2: Run, confirm fail.**

- [ ] **Step 7.3: Implement `ActionsRow.svelte`**

```svelte
<script lang="ts">
  import type { JobState } from "../lib/stores";
  import type { LifecycleAction } from "../lib/tauri";

  let { project, activeJob, onRun, onConfirm, onCancel }: {
    project: string;
    activeJob: JobState | null;
    onRun: (action: LifecycleAction) => void;
    onConfirm: (action: "rebuild" | "destroy") => void;
    onCancel: () => void;
  } = $props();
</script>

<div class="actions">
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
```

(`project` is currently unused in the markup but is part of the component's contract — the parent passes it and it documents which project the row acts on; keep it for clarity and future per-action labels. If the linter flags it as unused, prefix-bind it where needed in Task 9's composition instead.)

- [ ] **Step 7.4: Run, confirm pass. Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/lib/components/ActionsRow.svelte gui/src/lib/components/ActionsRow.test.ts
git commit -m "$(cat <<'EOF'
Add ActionsRow (lifecycle buttons, Cancel-while-running)

Up/Down/Update fire directly; Rebuild/Destroy request confirmation
via callback (parent wires the modal). Collapses to Cancel during an
active job.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `Sidebar.svelte`

**Files:** Create `gui/src/lib/components/Sidebar.svelte`, `.test.ts`.

Project list with a status LED (color keyed by effective status) and click-to-select. Takes `projects`, `jobs`, `selectedName`, and an `onSelect` callback.

- [ ] **Step 8.1: Write the failing test**

```ts
import { render, fireEvent } from "@testing-library/svelte";
import { describe, it, expect, vi } from "vitest";
import Sidebar from "./Sidebar.svelte";
import type { ProjectStatus } from "../lib/tauri";

function p(name: string, status: string): ProjectStatus {
  return { name, status, uptime_seconds: null, cpu_percent: null,
    mem_used_bytes: null, mem_total_bytes: null, primary_repo: null,
    branch: null, idle_seconds: null, ports: [], profiles: [], repos: [] };
}

describe("Sidebar", () => {
  it("lists projects and fires onSelect", async () => {
    const onSelect = vi.fn();
    const { getByText } = render(Sidebar, {
      props: { projects: [p("wallet", "Running"), p("blog", "Stopped")],
        jobs: new Map(), selectedName: "wallet", onSelect },
    });
    await fireEvent.click(getByText("blog"));
    expect(onSelect).toHaveBeenCalledWith("blog");
  });

  it("marks the running project's LED", () => {
    const { container } = render(Sidebar, {
      props: { projects: [p("wallet", "Running")], jobs: new Map(),
        selectedName: "wallet", onSelect: () => {} },
    });
    expect(container.querySelector(".led.running")).not.toBeNull();
  });
});
```

- [ ] **Step 8.2: Run, confirm fail.**

- [ ] **Step 8.3: Implement `Sidebar.svelte`**

```svelte
<script lang="ts">
  import type { ProjectStatus, JobId } from "../lib/tauri";
  import { effectiveStatus, type JobState } from "../lib/stores";

  let { projects, jobs, selectedName, onSelect }: {
    projects: ProjectStatus[];
    jobs: Map<JobId, JobState>;
    selectedName: string | null;
    onSelect: (name: string) => void;
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
</nav>

<style>
  .sidebar { width: 180px; border-right: 1px solid var(--border);
    background: var(--sidebar-bg); padding: 8px 0; }
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
```

- [ ] **Step 8.4: Run, confirm pass. Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/lib/components/Sidebar.svelte gui/src/lib/components/Sidebar.test.ts
git commit -m "$(cat <<'EOF'
Add Sidebar (project list, effective-status LED, selection)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `list_profiles` command + `DetailPanel.svelte`

**Files:** Modify `gui/src-tauri/src/cli.rs`, `gui/src-tauri/src/lib.rs`, `gui/src/lib/tauri.ts`; create `gui/src/lib/components/DetailPanel.svelte`, `.test.ts`.

`list_profiles` (needed by Task 10's FirstRunModal) lists profile basenames. `DetailPanel` composes the header + StatsBar + ActionsRow + LogPane and owns the per-project confirm-modal gating.

- [ ] **Step 9.1: Add the profile lister to `cli.rs`**

The first-run dropdown needs the set of available profile names. The CLI has no JSON command for this, and adding one is plan-1 scope. So: in a dev checkout, read `profiles/*.toml` basenames directly; in a release build (where the data tree's location depends on the Homebrew layout), fall back to the known bundled set. This is a directory listing, not config parsing, so it doesn't violate "the GUI doesn't parse config." Add to `cli.rs`:

```rust
pub const BUNDLED_PROFILES: &[&str] =
    &["cypress", "python", "rust", "go", "supabase-fly"];

/// Available profile names. In a dev checkout, read profiles/*.toml; otherwise
/// fall back to the known bundled set. (A future CLI `profiles --json` command
/// would let this stop guessing — tracked for a later pass.)
pub fn list_profile_names() -> Vec<String> {
    if cfg!(debug_assertions) {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../profiles");
        if let Ok(entries) = std::fs::read_dir(&dir) {
            let mut names: Vec<String> = entries
                .flatten()
                .filter_map(|e| {
                    let p = e.path();
                    if p.extension()?.to_str()? == "toml" {
                        Some(p.file_stem()?.to_string_lossy().to_string())
                    } else { None }
                })
                .collect();
            names.sort();
            if !names.is_empty() { return names; }
        }
    }
    BUNDLED_PROFILES.iter().map(|s| s.to_string()).collect()
}
```

> The `BUNDLED_PROFILES` constant must stay in sync with the actual `profiles/*.toml` files shipped by the CLI. If profiles are added/removed in the repo, update this list (or replace the whole thing with a `machine profiles --json` command in a later CLI pass — the cleaner long-term fix).

- [ ] **Step 9.2: Add the command to `lib.rs`** and register it:

```rust
#[tauri::command]
fn list_profiles() -> Vec<String> {
    cli::list_profile_names()
}
```

Add `list_profiles` to `generate_handler!`. `cargo check` clean; add a quick unit test in `cli.rs`:

```rust
#[test]
fn list_profile_names_nonempty() {
    // Dev checkout has profiles/*.toml; release falls back to BUNDLED_PROFILES.
    assert!(!list_profile_names().is_empty());
}
```

Run `cargo test cli::`.

- [ ] **Step 9.3: Add `listProfiles` to `tauri.ts`**

```ts
// in the `api` object:
listProfiles: () => invoke<string[]>("list_profiles"),
```

- [ ] **Step 9.4: Write `DetailPanel.test.ts`**

```ts
import { render } from "@testing-library/svelte";
import { describe, it, expect } from "vitest";
import DetailPanel from "./DetailPanel.svelte";
import type { ProjectStatus } from "../lib/tauri";

const proj: ProjectStatus = {
  name: "wallet", status: "Running", uptime_seconds: 8040, cpu_percent: 2.1,
  mem_used_bytes: 1_932_735_283, mem_total_bytes: 8_589_934_592,
  primary_repo: "wallet", branch: "main", idle_seconds: 180,
  ports: [3000], profiles: ["cypress"], repos: [],
};

describe("DetailPanel", () => {
  it("shows the project header and status", () => {
    const { getByText } = render(DetailPanel, {
      props: { project: proj, jobs: new Map(),
        onRun: () => {}, onConfirm: () => {}, onCancel: () => {} },
    });
    expect(getByText("wallet")).toBeInTheDocument();
    expect(getByText(/Running/)).toBeInTheDocument();
    expect(getByText(/2h 14m/)).toBeInTheDocument(); // uptime 8040s
  });
});
```

- [ ] **Step 9.5: Implement `DetailPanel.svelte`**

```svelte
<script lang="ts">
  import type { ProjectStatus, JobId, LifecycleAction } from "../lib/tauri";
  import { activeJobFor, effectiveStatus, type JobState } from "../lib/stores";
  import { formatDuration } from "../lib/format";
  import StatsBar from "./StatsBar.svelte";
  import ActionsRow from "./ActionsRow.svelte";
  import LogPane from "./LogPane.svelte";

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
        {#if shownJob.done}<span class="exit" class:fail={shownJob.exitCode !== 0}>
          exit {shownJob.exitCode}</span>{:else}<span class="running">running…</span>{/if}
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
```

- [ ] **Step 9.6: Run tests (`cargo test cli::` + `pnpm test`), confirm pass. Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src-tauri gui/src/lib/tauri.ts gui/src/lib/components/DetailPanel.svelte gui/src/lib/components/DetailPanel.test.ts
git commit -m "$(cat <<'EOF'
Add list_profiles command and DetailPanel composition

list_profiles lists profile names (dev: reads profiles/*.toml;
release: bundled fallback). DetailPanel composes header + StatsBar +
ActionsRow + LogPane and shows the latest job's log.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `FirstRunModal.svelte` + `EmptyState.svelte`

**Files:** Create `gui/src/lib/components/FirstRunModal.svelte`, `.test.ts`, `gui/src/lib/components/EmptyState.svelte`.

First-run/empty: name (validated `^[a-z0-9][a-z0-9-]*$`), repo URL (non-empty), profile (multi-select from `list_profiles`). Submit → `add_project`. EmptyState wraps it with "Reveal in Finder" / "Docs" affordances.

- [ ] **Step 10.1: Write the failing test** — `FirstRunModal.test.ts`:

```ts
import { render, fireEvent } from "@testing-library/svelte";
import { describe, it, expect, vi } from "vitest";
import FirstRunModal from "./FirstRunModal.svelte";

describe("FirstRunModal", () => {
  it("disables submit until name + repo are valid", async () => {
    const onSubmit = vi.fn();
    const { getByRole, getByLabelText } = render(FirstRunModal, {
      props: { profiles: ["cypress", "go"], onSubmit, onSkip: () => {} },
    });
    const submit = getByRole("button", { name: /create/i });
    expect(submit).toBeDisabled();
    await fireEvent.input(getByLabelText(/name/i), { target: { value: "myproj" } });
    expect(submit).toBeDisabled(); // repo still empty
    await fireEvent.input(getByLabelText(/repo/i),
      { target: { value: "git@github.com:me/x.git" } });
    expect(submit).not.toBeDisabled();
    await fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith({
      name: "myproj", repo: "git@github.com:me/x.git", profiles: [],
    });
  });

  it("rejects an invalid name", async () => {
    const { getByRole, getByLabelText } = render(FirstRunModal, {
      props: { profiles: [], onSubmit: () => {}, onSkip: () => {} },
    });
    await fireEvent.input(getByLabelText(/name/i), { target: { value: "Bad_Name" } });
    await fireEvent.input(getByLabelText(/repo/i), { target: { value: "x" } });
    expect(getByRole("button", { name: /create/i })).toBeDisabled();
  });
});
```

- [ ] **Step 10.2: Run, confirm fail.**

- [ ] **Step 10.3: Implement `FirstRunModal.svelte`**

```svelte
<script lang="ts">
  let { profiles, onSubmit, onSkip }: {
    profiles: string[];
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

<div class="backdrop" role="presentation">
  <div class="modal" role="dialog" aria-modal="true">
    <h2>Add your first project</h2>
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
      <button onclick={onSkip}>Skip</button>
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
```

- [ ] **Step 10.4: Implement `EmptyState.svelte`**

```svelte
<script lang="ts">
  import { api } from "../lib/tauri";
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
```

> Note: `EmptyState`'s "Reveal config in Finder" reuses `open_logs` for now (reveals the state dir). A dedicated "reveal projects.toml" reveal is a minor follow-up; not worth a new command in v1.

- [ ] **Step 10.5: Run, confirm pass. Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/lib/components/FirstRunModal.svelte gui/src/lib/components/FirstRunModal.test.ts gui/src/lib/components/EmptyState.svelte
git commit -m "$(cat <<'EOF'
Add FirstRunModal + EmptyState

First-run form validates name (^[a-z0-9][a-z0-9-]*$) and repo, picks
profiles from list_profiles, and calls add_project. EmptyState wraps
it for the no-projects case.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: `DoctorBanner.svelte`

**Files:** Create `gui/src/lib/components/DoctorBanner.svelte`, `.test.ts`.

Runs `run_doctor` on mount; if `summary.fails > 0`, shows a yellow banner; clicking expands a drawer listing failed checks + hints.

- [ ] **Step 11.1: Write the failing test** (mock the api):

```ts
import { render, fireEvent, waitFor } from "@testing-library/svelte";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/tauri", () => ({
  api: { runDoctor: vi.fn() },
}));
import { api } from "../lib/tauri";
import DoctorBanner from "./DoctorBanner.svelte";

describe("DoctorBanner", () => {
  beforeEach(() => vi.clearAllMocks());

  it("hidden when all checks pass", async () => {
    (api.runDoctor as any).mockResolvedValue({
      checks: [{ name: "limactl on PATH", status: "ok", detail: null, hint: null }],
      summary: { checks: 1, fails: 0 },
    });
    const { container } = render(DoctorBanner, {});
    await waitFor(() => expect(api.runDoctor).toHaveBeenCalled());
    expect(container.querySelector(".banner")).toBeNull();
  });

  it("shows failures and expands hints", async () => {
    (api.runDoctor as any).mockResolvedValue({
      checks: [{ name: "SSH_AUTH_SOCK unset", status: "fail", detail: null,
        hint: "start your SSH agent" }],
      summary: { checks: 1, fails: 1 },
    });
    const { getByText, queryByText } = render(DoctorBanner, {});
    await waitFor(() => getByText(/1 check failed/i));
    expect(queryByText("start your SSH agent")).toBeNull(); // collapsed
    await fireEvent.click(getByText(/1 check failed/i));
    expect(getByText("start your SSH agent")).toBeInTheDocument();
  });
});
```

- [ ] **Step 11.2: Run, confirm fail.**

- [ ] **Step 11.3: Implement `DoctorBanner.svelte`**

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import { api, type DoctorReport } from "../lib/tauri";

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
```

- [ ] **Step 11.4: Run, confirm pass. Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/lib/components/DoctorBanner.svelte gui/src/lib/components/DoctorBanner.test.ts
git commit -m "$(cat <<'EOF'
Add DoctorBanner (run_doctor on mount, expandable failures)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Compose everything in `+page.svelte` + job-event ingestion

**Files:** Modify `gui/src/routes/+page.svelte` (the file 2a created).

Replace the 2a inline slice with the components. Owns: initial load, `projects://updated` subscription, job spawning + event ingestion into the `jobs` store, the confirm-modal and first-run-modal gating. Async listener cleanup uses `onDestroy` (Svelte requires a *sync* cleanup from `onMount`), matching the pattern 2a established in this file.

- [ ] **Step 12.1: Rewrite `gui/src/routes/+page.svelte`**

```svelte
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
  let firstRun = $state(false);
  let availableProfiles = $state<string[]>([]);
  let error = $state<string | null>(null);
  let unlistenProjects: (() => void) | null = null;

  onMount(async () => {
    try {
      $projects = await api.listProjects();
      if (!$selectedName && $projects.length) $selectedName = $projects[0].name;
      if ($projects.length === 0) firstRun = true;
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
        // Auto-collapse handled implicitly: DetailPanel keeps showing the last
        // job; a future tick could clear successful ones after 3s. Keep simple.
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
      firstRun = false;
    } catch (e) { error = String(e); }
  }
</script>

<DoctorBanner />
{#if error}<div class="errbar">{error}</div>{/if}

<div class="layout">
  <Sidebar projects={$projects} jobs={$jobs} selectedName={$selectedName}
    onSelect={(n) => ($selectedName = n)} />
  {#if $selectedProject}
    <DetailPanel project={$selectedProject} jobs={$jobs}
      {onRun} {onConfirm} {onCancel} />
  {:else}
    <EmptyState onAdd={() => (firstRun = true)} />
  {/if}
</div>

{#if confirming}
  <ConfirmDestroyModal project={confirming.project} action={confirming.action}
    onConfirm={confirmYes} onCancel={() => (confirming = null)} />
{/if}
{#if firstRun}
  <FirstRunModal profiles={availableProfiles}
    onSubmit={firstRunSubmit} onSkip={() => (firstRun = false)} />
{/if}

<style>
  .layout { display: flex; height: 100vh; }
  .errbar { background: #fdecea; color: #c0392b; padding: 6px 14px; font-size: 12px; }
</style>
```

- [ ] **Step 12.2: Run the app end-to-end**

```bash
cd gui
MACHINE_BIN=../bin/machine pnpm tauri dev
```

Manual checklist:
1. Sidebar lists projects with correct LED colors.
2. Selecting shows DetailPanel with formatted stats + uptime.
3. **Up** streams output; the row collapses to **Cancel**; the project shows **Provisioning** in the sidebar while running.
4. **Destroy** opens the confirm modal; the button stays disabled until you type the exact name; confirming runs it.
5. With an empty `projects.toml` (rename yours aside), the FirstRunModal appears; submitting creates the project and it shows up.
6. If `machine doctor --json` reports a failure (e.g. unset signing key), the yellow banner appears and expands.

- [ ] **Step 12.3: Run all tests + typecheck**

```bash
cd gui && pnpm test && pnpm exec svelte-check
cd src-tauri && cargo test
```

Expected: all green.

- [ ] **Step 12.4: Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/routes/+page.svelte
git commit -m "$(cat <<'EOF'
Compose the full UI in +page.svelte

Replaces the 2a slice: Sidebar + DetailPanel + EmptyState, with
job-event ingestion into the jobs store, confirm-modal gating for
destroy/rebuild, the first-run modal, and the doctor banner.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: macOS styling pass

**Files:** Modify `gui/src/app.css` (the scaffold's global stylesheet).

Define the CSS variables the components reference and the macOS look (system font, hairline borders, subtle backgrounds). This is visual — verified by eye, not by test.

- [ ] **Step 13.1: Create `gui/src/app.css`**

```css
:root {
  --text: #1a1a1c;
  --muted: #6b6b70;
  --border: #e2e2e6;
  --sidebar-bg: #f7f7f9;
  --panel: #ffffff;
  --tile-bg: #f3f3f5;
  --btn: #ffffff;
  --selection: #d8e6ff;
  --accent: #007aff;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
  color: var(--text);
  font-size: 13px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --text: #ececf0; --muted: #9a9aa0; --border: #38383c;
    --sidebar-bg: #1c1c1e; --panel: #242426; --tile-bg: #2c2c2e;
    --btn: #2c2c2e; --selection: #0a3a6b; --accent: #0a84ff;
    background: #1c1c1e;
  }
  body { background: #1c1c1e; }
}

* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
button { font-family: inherit; color: inherit; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
```

- [ ] **Step 13.2: Wire `app.css` via a `+layout.svelte`**

SvelteKit has no `main.ts`; global styles are imported from a layout. Create `gui/src/routes/+layout.svelte` (it coexists with the existing `+layout.ts`):

```svelte
<script lang="ts">
  import "../../app.css";
  let { children } = $props();
</script>

{@render children()}
```

(`../../app.css` resolves from `src/routes/` to `src/app.css`. The `{@render children()}` is the Svelte 5 slot form a layout needs so the page still renders.)

- [ ] **Step 13.3: Fix the window title in `app.html`**

The scaffold left `<title>Tauri + SvelteKit + Typescript App</title>` in `gui/src/app.html`. Change it to `<title>machine</title>`.

- [ ] **Step 13.4: Visual check**

`MACHINE_BIN=../bin/machine pnpm tauri dev` — confirm: system font, hairline sidebar divider, LED colors (green/grey/red/amber), selected row highlight, dark-mode follows the OS. Compare against the mockup from brainstorming (layout option A).

- [ ] **Step 13.5: Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src/app.css gui/src/routes/+layout.svelte gui/src/app.html
git commit -m "$(cat <<'EOF'
Add macOS styling pass (CSS variables, light/dark)

Defines the design tokens the components reference: system font,
hairline borders, tile/selection colors, and a dark-mode palette that
follows the OS. Wires app.css via +layout.svelte and fixes the window
title.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist (for the implementer)

- [ ] `cd gui && pnpm test` — all component + unit tests pass.
- [ ] `cd gui && pnpm exec svelte-check` — no type errors.
- [ ] `cd gui/src-tauri && cargo test` — `list_profiles` test passes; prior tests intact.
- [ ] `MACHINE_BIN=../bin/machine pnpm tauri dev` — the Task 12 manual checklist passes end-to-end, and the Task 13 visual check matches mockup A.
- [ ] Provisioning status shows while an up/rebuild job runs (sidebar LED amber).
- [ ] Destroy/rebuild require typing the exact project name; up/down/update are single-click.
- [ ] First-run modal appears on an empty `projects.toml` and creates a working project via `add_project`.
- [ ] Doctor banner appears only when `doctor --json` reports failures.
- [ ] No CLI logic duplicated in the frontend; every state change goes through a Tauri command.
- [ ] Commits signed (retry on agent failure; never `--no-gpg-sign`).

Once green, the GUI is feature-complete for v1 — proceed to **plan 3** (`docs/superpowers/plans/2026-05-26-gui-plan-3-packaging.md`, to be written): universal `.dmg` build in CI on tag, ad-hoc signing, and the `Casks/machine-gui.rb` Homebrew cask depending on the `machine` formula.
```
