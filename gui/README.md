# machine GUI

A Tauri + Svelte desktop app over the `machine` CLI. macOS-first.

## Dev

Requires Rust (`rustup`), Node ≥ 20, pnpm. From `gui/`:

```sh
pnpm install
MACHINE_BIN=../bin/machine pnpm tauri dev
```

In a dev build the backend resolves the CLI from `$MACHINE_BIN`, else
`../../bin/machine` relative to `src-tauri/`, else `machine` on `PATH`.
`projects.toml` resolves via `$PROJECTS_FILE` / `$MACHINE_CONFIG_DIR`, else the
repo checkout's `projects.toml`, else `~/.config/machine/projects.toml`.

## Layout

The scaffolder emits a SvelteKit app (adapter-static, SPA mode), so the UI
lives in `src/routes/+page.svelte` and shared code under `src/lib` (`$lib`).

- `src-tauri/src/types.rs` — serde mirrors of the `machine --json` contract
- `src-tauri/src/cli.rs` — binary/path resolution + run-and-parse
- `src-tauri/src/jobs.rs` — lifecycle subprocess streaming
- `src-tauri/src/poll.rs` — `ps --json` polling → `projects://updated`
- `src-tauri/src/watcher.rs` — `projects.toml` watcher
- `src/lib/tauri.ts` — typed `invoke`/`listen` client
- `src/lib/stores.ts` — `projects` / `jobs` / `selectedName`
- `src/routes/+page.svelte` — UI

## Tests

```sh
cd src-tauri && cargo test    # Rust: type-parse + helpers
pnpm check                    # frontend types (svelte-kit sync + svelte-check)
```
