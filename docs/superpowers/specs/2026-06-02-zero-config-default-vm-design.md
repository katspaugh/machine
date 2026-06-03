# Zero-config default VM

**Date:** 2026-06-02
**Status:** Approved

## Goal

Let people launch a base VM out of the box, without running `machine init` or
editing `projects.toml` first. The config file becomes opt-in: you add it when
you want repos cloned, profiles, or a non-default shell.

Two behaviors:

1. Bare `machine up` (no project argument) launches a base VM named `default`
   — no repos, no profiles, no config file required.
2. `machine up <name>` with a name that is not in `projects.toml` (or with no
   config file at all) offers to create a base VM with that name instead of
   erroring.

## Non-goals

- Persisting ad-hoc VMs into `projects.toml`. The CLI never writes to the
  config file; it stays purely declarative and hand-edited.
- Inferring projects from the current directory or accepting git URLs as
  project arguments.
- Changing `machine init`, `projects.toml.example`, or profile semantics.

## Design

### 1. Config loading

`load_projects()` returns `{}` when `PROJECTS_FILE` is missing, instead of
dying. `get_project()` keeps its hard `die("project '<name>' not in ...")` —
the config-reading callers (`project_urls`, `project_profiles`) still surface
that error for unknown names. `cmd_secrets` doesn't read the config at all; it
operates on the VM name directly (see Error handling).

### 2. `cmd_up` resolution

`cmd_up` loads the config once and branches on `name in cfg`:

- **Known project:** exactly today's path — repos, profiles, reachability
  check, clone loop.
- **Unknown project:** confirm before creating:

  ```
  No project '<name>' in <PROJECTS_FILE> — create a base VM? [y/N]
  ```

  Abort on anything but `y`; catch `EOFError` so non-tty input aborts cleanly
  instead of tracebacking. The prompt is skipped when the VM already exists —
  re-running `up` on an existing ad-hoc VM stays non-interactive, matching
  `up`'s idempotent re-provisioning contract. The name `default` skips the prompt
  so bare `machine up` is fully non-interactive. Then proceed with
  `urls = []` and profiles resolved through the existing `default_profile`
  fallback (`[default_profile]` if set, else `[]`) — an ad-hoc VM behaves
  exactly like a configured project with no `repos`/`profiles` keys.
  `verify_repos_reachable([])` and the clone loop are no-ops on empty lists.

The typo-safety rationale: `machine up blgo` must not silently spend minutes
booting a fresh empty VM when the user meant `blog`.

### 3. CLI surface

The `project` positional becomes `nargs="?"`, `default="default"` on `up`,
`down`, `ssh`, `claude`, `destroy`, and `secrets`, so e.g. bare `machine ssh`
enters the default VM.

**Exception:** `run` keeps a required project argument — its trailing
`argv` remainder makes an optional project ambiguous (`machine run echo hi`:
is `echo` the project or the command?).

`up`'s help text mentions the zero-config default. Shell completions under
`completions/` are updated if they enumerate positional args.

### 4. `machine list` without a config

`cmd_list` works with no config file: missing file → `{}` via the
`load_projects()` change, so it prints `limactl list` and simply omits the
"configured but not created" section.

### 5. Preserved behaviors

Already in place, no changes needed:

- `project_shell()` tolerates a missing config (zsh fallback, honors
  `default_shell` when the file exists).
- `_primary_repo_workdir()` handles projects without repos (returns `None`,
  shell opens in `$HOME`).
- `down`/`destroy`/`run` operate on the Lima VM name directly.

### 6. Docs

README quickstart gains the zero-config path ("`machine up` — no config
needed; add `projects.toml` when you want repos/profiles"). Same change in
`docs/docs/index.html`.

## Error handling

- Invalid names are still rejected by `validate_name()` before anything else.
- Declining the confirm prompt exits non-zero with `aborted`.
- `machine secrets <name>` for an unknown name does not error on the config —
  `cmd_secrets` works off the VM name directly. It runs against the named VM
  and reports "no repos with `use op_env`" (or a Lima not-found error if the
  VM doesn't exist), which is the right behavior in the zero-config world.

## Testing

Host-side unit tests in `tests/unit/test_machine.py` (run via
`tests/unit.sh`, no VM required):

- `load_projects()` returns `{}` when the file is missing.
- Parser: `machine up` defaults `project` to `default`; same for `down`,
  `ssh`, `claude`, `destroy`, `secrets`; `run` still requires it.
- Unknown-name resolution: prompt accepted → proceeds with empty repos;
  declined → aborts; `default` skips the prompt.
- Profiles for ad-hoc names: `[]` with no config / no `default_profile`;
  `[<p>]` when top-level `default_profile = "<p>"` is set.
