# `machine.app` — GUI for the `machine` CLI

**Status:** design
**Date:** 2026-05-26

## Goal

A Docker-Desktop-style macOS app that lists every project from `projects.toml`, shows live VM status, and lets the user run lifecycle actions (up, down, update, rebuild, destroy) without dropping to a terminal. The GUI is a thin shell over the existing `bin/machine` CLI — the CLI stays the single source of truth for parsing config, driving Lima, and provisioning. Both CLI and GUI are first-class entry points: power users keep the terminal, new users get a desktop app.

## Non-goals (v1)

- **Editing existing projects in the GUI.** Beyond the first-run "add project" modal, `projects.toml` editing is deferred to v2.
- **Embedded terminal / SSH client.** SSH and Claude buttons (post-v1) shell out to Terminal.app.
- **Linux or Windows.** `machine` itself is macOS-first via Lima; the GUI matches.
- **Secrets UI.** `machine secrets` stays CLI-only — Touch ID flows are awkward to mediate through a GUI subprocess.
- **Auto-update of the app binary.** Homebrew Cask handles upgrades.

## Architecture

Three processes, strictly layered:

```
machine.app  ──►  bin/machine  ──►  limactl  ──►  Lima VM
  (Tauri)        (Python CLI)      (unchanged)
```

The GUI never invokes `limactl` directly and never parses `projects.toml` beyond a shallow schema check; every state change flows through the CLI. Two interaction patterns:

- **Query** — every 2s while the window is focused, the Rust backend runs `machine ps --json`, parses, and emits a Tauri event to the renderer. Backs off to 15-30s when blurred.
- **Lifecycle** — on click, Rust spawns `machine <action> <project> --plain` via `tokio::process::Command`. Each stdout/stderr line is forwarded as a Tauri event to the log pane.

A `notify`-crate watcher on `CONFIG_DIR/projects.toml` triggers an immediate refresh when the user edits the file in `$EDITOR`.

## CLI changes

Three existing commands grow a `--json` flag — no new top-level subcommands for status:

- `machine ps --json` — JSON array, one entry per project ∪ VM
- `machine list --json` — static `projects.toml` view (config only, no VM probing)
- `machine doctor --json` — `{checks: [{name, status, hint?}]}` for the diagnostics banner

`ps --json` shape:

```json
{
  "name": "wallet",
  "status": "Running",
  "uptime_seconds": 8040,
  "cpu_percent": 2.1,
  "mem_used_bytes": 1932735283,
  "mem_total_bytes": 8589934592,
  "primary_repo": "safe-wallet-monorepo",
  "branch": "main",
  "idle_seconds": 180,
  "ports": [3000, 5173],
  "profiles": ["cypress"],
  "repos": ["git@github.com:..."]
}
```

`status` is one of `Running | Stopped | Missing | Provisioning`. All quantities are raw machine-readable numbers — the GUI formats them. Fields that are unknown for a stopped VM are `null` (not the em-dash strings the table renderer uses).

One new subcommand:

- `machine config add-project <name> --repo <url> [--profile <p>...]` — append-only writer for the first-run modal. Refuses to overwrite existing entries; validates against `schemas/projects.schema.json` before writing. Keeps all `projects.toml` mutation in Python.

Lifecycle commands (`up`, `down`, `update`, `rebuild`, `destroy`) already accept `--plain` — the GUI uses that and parses stdout line-by-line. No additional flags needed.

## Tauri backend (Rust)

Crate at `gui/src-tauri/`. Resolves `bin/machine` in this order: `MACHINE_BIN` env var (escape hatch), `../bin/machine` relative to the crate when `cfg!(debug_assertions)` is true (dev mode), otherwise plain `machine` from `PATH` (release; Homebrew puts it there). Seven `#[tauri::command]` handlers:

```rust
list_projects() -> Vec<ProjectStatus>          // machine ps --json
list_config()   -> Vec<ProjectConfig>          // machine list --json
run_doctor()    -> DoctorReport                // machine doctor --json
add_project(name, repo, profiles) -> ()        // machine config add-project ...
spawn_lifecycle(project, action) -> JobId      // up/down/update/rebuild/destroy
cancel_job(job_id) -> ()                       // SIGTERM the subprocess
open_logs(project) -> ()                       // reveal log dir in Finder
```

### Jobs

`spawn_lifecycle` allocates a `JobId`, spawns the subprocess in a tokio task, and returns immediately. Per-job state lives in `tokio::Mutex<HashMap<JobId, JobState>>` on the Rust side, so closing/reopening the log pane reattaches to the still-running subprocess.

Each subprocess line is emitted as a Tauri event:

```
job://{job_id}/log    { line: "...", stream: "stdout" | "stderr" }
job://{job_id}/done   { exit_code: i32, duration_ms: u64 }
```

Concurrency: one active job per project. Different projects can run concurrently — `machine` already supports parallel `up`s.

### Polling task

A single tokio task started at app launch:

1. Sleep `interval` (2s when window focused, 30s when blurred).
2. Run `list_projects()`.
3. Diff against previous result; if changed, emit `projects://updated` with the new list.

Window focus/blur transitions reset the interval immediately so the user gets a fresh read the moment they tab back to the app.

## Frontend (renderer)

Stack: **Vite + Svelte 5 + TypeScript**, plain CSS. No router (single-pane app), no global state library (two Svelte stores).

Component tree:

```
App.svelte
├── DoctorBanner.svelte           — yellow if doctor reports failures
├── Sidebar.svelte                — project list, status LED, click-to-select
├── DetailPanel.svelte
│   ├── Header                    — name, status pill, profile chips, uptime
│   ├── StatsBar.svelte           — CPU / mem / idle / ports tiles
│   ├── ActionsRow.svelte         — Up / Down / Update / Rebuild / Destroy
│   └── LogPane.svelte            — streaming subprocess output, collapsible
├── ConfirmDestroyModal.svelte    — type-project-name to confirm
└── FirstRunModal.svelte          — appears when projects.toml is empty
```

Stores:

```ts
projects:     writable<ProjectStatus[]>
jobs:         writable<Map<JobId, JobState>>
selectedName: writable<string | null>
```

Plus a derived `selectedProject` matching `projects` by name (stable across polling refreshes; survives the project being destroyed externally — selection moves to the next entry).

LogPane auto-scrolls unless the user has scrolled up (then a "Jump to bottom" button appears). After job completion, the pane persists in the DOM until the user dismisses it, so they can read what happened.

Styling: macOS look — system font (`-apple-system`), hairline borders, subtle gradients. Inline SVG for status LEDs and action icons; no custom icon font.

## UX details

### Lifecycle buttons

While a job is active for the selected project, the action row collapses to a single "Cancel" button which sends SIGTERM to the subprocess (the CLI is idempotent, so a half-done `up` re-runs cleanly). On success the log pane auto-collapses after 3s; on failure it stays open.

### Destructive actions

Rebuild and Destroy require typing the project name into a confirmation modal (GitHub-style). Friction is proportional to risk; the rest of the lifecycle is single-click.

### First-run

If `projects.toml` does not exist: GUI calls `machine init` (which writes the bundled example), then opens FirstRunModal. Fields: name (validated against `[a-z0-9-]+`), primary repo URL, profile (dropdown populated from `profiles/*.toml`). Submit → `machine config add-project ...` → reload list. If the user skips, the empty-state pane shows: "No projects yet — edit `~/.config/machine/projects.toml` to add one. [Reveal in Finder] [Docs]".

### Errors

A failed lifecycle job turns the row LED red and keeps the log pane open with the last 50 lines + "Open full log" (reveals `~/.local/state/machine/logs/<vm>-*.log` in Finder). `doctor --json` failures surface as a yellow banner across the top of the app on launch; click expands a drawer with per-check status and CLI-equivalent hints.

### App lifecycle

Regular Dock app, single-instance: launching `machine.app` again brings the existing window to the front instead of opening a second one. Closing the last window quits (no menu-bar widget in v1).

## Repo layout

```
gui/
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   └── src/
│       ├── main.rs           # entry, registers commands + polling task
│       ├── cli.rs            # subprocess spawning, JSON parsing
│       ├── jobs.rs           # JobId allocator, job state map
│       ├── watcher.rs        # notify-crate projects.toml watcher
│       └── types.rs          # ProjectStatus, DoctorReport, JobId
├── src/                      # Svelte frontend
│   ├── main.ts
│   ├── App.svelte
│   ├── lib/
│   │   ├── stores.ts
│   │   └── tauri.ts          # typed wrappers for invoke() / event listen()
│   └── components/*.svelte
├── package.json
├── tsconfig.json
├── vite.config.ts
└── README.md                 # gui dev workflow
```

## Packaging

- CI builds a universal `.dmg` (x86_64 + arm64) on git tag. Ad-hoc signed initially; Developer ID signing + notarization once an Apple Developer account is available.
- New `Casks/machine-gui.rb` in `katspaugh/homebrew-machine`: `brew install --cask machine-gui`. Cask depends on the existing `machine` formula so the CLI is guaranteed to be present.
- App version tracks the CLI version (single repo, single tag). No runtime version check between app and CLI — Homebrew pairs them via the Cask dependency.

## Testing

- **Rust:** `cargo test` for the JSON-parsing layer (snapshot tests against fixture stdout from each `--json` command) and the watcher debounce logic. No live Tauri runtime needed.
- **Frontend:** Vitest + `@testing-library/svelte` for component logic — selection-by-name, log-pane scroll-lock, modal validation, store derivation.
- **CLI side:** extend `tests/unit.sh` with fixture tests for `ps --json`, `list --json`, `doctor --json` output, and for `config add-project` (idempotency, schema rejection, name-collision rejection).
- **E2E:** out of scope for v1. Real-VM smoke is already covered by `tests/run-all.sh`; piling Playwright on a `.app` adds CI complexity that doesn't pay back at this size.

## Alternatives considered

- **Electron** — ruled out for the ~150MB Chromium bundle and heavier toolchain; nothing the renderer needs requires a specific Chromium feature.
- **Local-server + browser** (`machine gui` opens a localhost URL) — ruled out because launching from a terminal command defeats the "first-class for new users" goal. Could ship in parallel for headless/remote use if a future need appears.
- **Long-running `machine` daemon over a Unix socket** — overkill for a 2s polling loop. Worth revisiting only if we add live event streaming deeper than per-job stdout.
- **GUI parses `projects.toml` directly in Rust** — duplicates the schema and merge logic that lives in `bin/machine` and `provision/run.py`. Cheaper short-term, expensive long-term as the CLI evolves.
