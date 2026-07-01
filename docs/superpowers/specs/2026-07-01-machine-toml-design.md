# `.machine.toml` — project config that lives in the repo

Status: approved design (core-only; folder-copy branch deliberately dropped)
Date: 2026-07-01

## Problem

`projects.toml` is host-local and gitignored. There is no way to ship a
project's VM configuration alongside its code, so every teammate (and every
machine you own) re-authors the same entry by hand — repos, profiles,
resources, shell. There is also friction in the common case: you are already
sitting in a repo's directory and just want a VM for *this*, but you still have
to name it and register it first.

`.machine.toml` closes both gaps: a small config file committed to (or fetched
into) a repo that `machine up` picks up automatically, "as if it were in
`projects.toml`".

## Scope

**In scope (this spec):**

- A `.machine.toml` file read from the current working directory.
- Bare `machine up` auto-detecting and using it.
- Deriving the VM name from the file or the directory basename.
- Resolving the code source: explicit `repos`, else the cwd git `origin`
  remote.
- Making the local project the ambient default for the other subcommands when
  your cwd is its directory.

**Explicitly out of scope (dropped after review):**

- Copying a non-git folder's contents into the VM. Narrow use case, most of the
  complexity and test surface, most surprising behavior (a one-time copy that
  then silently diverges from the host). A user who wants this can
  `git init && git commit` and fall through to the far more robust clone path.
  May revisit later with real demand behind it.

## File format

A `.machine.toml` uses **flat top-level keys** that mirror one `projects.toml`
table, plus an optional `name`:

```toml
# .machine.toml — every key is optional; an empty file is valid.
name          = "my-app"          # optional; defaults to sanitized dir basename
repos         = ["git@github.com:org/other.git"]  # optional
profiles      = ["cypress"]       # optional
shell         = "bash"            # optional; zsh|bash
forward_agent = false             # optional; default true
cpus          = 8                 # optional
memory        = "16GiB"           # optional
disk          = "60GiB"           # optional
```

Semantics of `repos`, `profiles`, `shell`, `forward_agent`, `cpus`, `memory`,
`disk` are **identical** to a `projects.toml` entry — they flow through the same
helpers (`project_profiles`, `project_shell`, `project_forward_agent`,
`project_resources`). Unknown keys are ignored, as they already are for
`projects.toml`.

An **empty file** is a complete, valid config meaning "make a VM for this
folder, inferring the repo from git".

### VM name resolution

1. If `name` is set in the file, use it (validated against `NAME_RE`,
   `[a-z0-9-]`; invalid → `die`).
2. Otherwise, sanitize the current directory's basename to `[a-z0-9-]`
   (lowercase; runs of other characters collapse to a single `-`; strip leading
   and trailing `-`). `~/Sites/My App` → `my-app`.
3. If sanitizing yields an empty string, `die` with a clear message asking the
   user to set `name` in `.machine.toml`.

## Architecture

### Local overlay in `load_projects()`

The integration point is a single overlay. `load_projects()` is split:

- `load_projects_file()` — the current body; reads and parses `PROJECTS_FILE`
  only.
- `load_projects()` — calls `load_projects_file()`, then, if the cwd has a
  parseable `.machine.toml`, adds its synthesized entry to the returned dict
  under the resolved name (**local file overrides** a same-named
  `projects.toml` entry).

Because every downstream helper already goes through `load_projects()`, the
local project transparently works everywhere: `project_urls`,
`project_profiles`, `project_shell`, `project_forward_agent`,
`project_resources`, `resolve_up_target`, `_primary_repo_workdir`. This is what
makes it behave "as if it were in `projects.toml`".

Invalid TOML in `.machine.toml` → `die` with the path and parse error (same
treatment `projects.toml` gets).

### Repo source folded into the overlay entry

To keep a single source of truth, the inferred remote is resolved **at overlay
construction time**, not scattered across commands:

- When the file lists `repos`, the entry keeps them as-is.
- When the file has no `repos`, `read_local_project()` queries the cwd for a git
  `origin` remote (`git config --get remote.origin.url`). If found, it sets the
  entry's `repos = [<origin-url>]`.
- If there is neither an explicit `repos` nor an `origin` remote, `repos` stays
  `[]` — a code-less VM (identical to a `projects.toml` `[bare]` entry). `cmd_up`
  prints a one-line note so this is not silent:
  `no repos in .machine.toml and no git remote — creating a code-less VM`.

Consequence: `project_urls`, `_primary_repo_workdir`, and the `cmd_up` clone
loop all see the same resolved repo list, so `machine ssh` opens at
`~/code/<repo-basename>` for an inferred remote with no special-casing.

### New helpers (host-side, in `bin/machine`)

- `slugify_name(s) -> str` — directory basename → `[a-z0-9-]`.
- `cwd_git_remote() -> str | None` — `git config --get remote.origin.url` in the
  cwd; `None` if not a repo / no origin.
- `read_local_project() -> tuple[str, dict] | None` — parse `./.machine.toml`,
  resolve the name, pop `name` out of the entry, fold in the inferred remote per
  above. Returns `(name, entry)` or `None` when the file is absent.
- `local_project_name() -> str | None` — `read_local_project()[0]` or `None`.
- `default_project() -> str` — `local_project_name()` if present, else
  `"default"`. The ambient target for bare subcommands (see below).

### `machine up` wiring

`resolve_up_project` gains a local-first branch:

- Bare `up` (no name): return `local_project_name()` if present; else the
  existing `default`-VM / wizard logic.
- Named `up <name>`: unchanged — but because the overlay already injected the
  local project into `cfg`, `machine up <name>` where `<name>` matches the local
  project resolves via `isinstance(cfg.get(name), dict)` and **never runs the
  wizard or writes to `projects.toml`**.

`cmd_up` prints a shadow note when the local file overrides a real
`projects.toml` entry (detected via `local_project_name() in
load_projects_file()`):
`.machine.toml shadows [<name>] in projects.toml — using the local file`.

Nothing about `.machine.toml` is ever written back to `projects.toml`;
portability is the whole point.

### Ambient default for other subcommands

Today `down`, `ssh`, `claude`, `destroy`, `secrets` default their `project`
argument to the literal `"default"`. To make the local project usable after
`machine up` without retyping its name, these default to `None` in argparse and
resolve via `name = args.project or default_project()`. In a `.machine.toml`
directory, bare `machine ssh` / `machine claude` / `machine down` reach the
local project; elsewhere they keep hitting `default`.

Addressing a local project **by name from outside its directory**
(`machine ssh my-app` from an unrelated cwd) is a known, documented limitation:
without the cwd file there is no config to resolve, so `machine` shells into the
VM at `$HOME` (the existing `_primary_repo_workdir` `try/except SystemExit`
already degrades gracefully) rather than opening at the repo. Users who need
name-addressing from anywhere should add the project to `projects.toml`.

## Error handling

- Invalid TOML → `die` with path + parse error.
- `name` present but invalid → `die` via `validate_name`.
- Directory basename sanitizes to empty and no `name` → `die` asking for
  `name`.
- Explicit `repos` unreachable → existing `verify_repos_reachable` behavior.
- No repos + no origin remote → note + code-less VM (not an error).

## Testing

Unit tests (`tests/unit/test_machine.py`, no VM required), driving a temp cwd
containing a `.machine.toml`:

- Name resolution: from `name` key; from dir basename; sanitization
  (`My App` → `my-app`); invalid `name` key → exit; empty-slug → exit.
- `read_local_project`: absent file → `None`; explicit `repos` preserved;
  no-`repos` + mocked `origin` remote → folded into `repos`; no-`repos` +
  no-remote → `repos == []`.
- `load_projects` overlay: local entry present in the returned cfg; local
  overrides a same-named `projects.toml` entry; `load_projects_file` unaffected.
- `resolve_up_project`: bare `up` in a `.machine.toml` dir returns the local
  name (does not fall through to wizard/`default`); named `up <local>` returns
  the name without invoking the wizard.
- `default_project`: local name when a file is present, `"default"` otherwise.

`cwd_git_remote` and any `git` calls are mocked. Existing tests run from the
repo root (no `.machine.toml`), so the overlay is inert and they are
unaffected.

## Documentation

- README: a "`.machine.toml`" section under Setup, covering the file, the
  name/repo inference, the bare-command ambient default, and the
  outside-the-directory limitation.
- `projects.toml.example`: a short pointer noting `.machine.toml` as the
  in-repo alternative.
- A committed `.machine.toml.example` at the repo root.
- `CHANGELOG.md`: an entry.

Completions are unaffected — no new subcommands or flags.
