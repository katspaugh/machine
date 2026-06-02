# Lima-native architecture — design

**Date:** 2026-06-02
**Status:** Approved

## Goal

Drastically simplify `machine` by deleting the GUI and replacing the
self-written provisioning system with Lima's native features. Same
capabilities, fewer and more standard parts. The repo's center of gravity
shifts from imperative Python to declarative Lima templates that `limactl`
executes directly.

## Why now

`bin/machine` (2,376 lines) plus `provision/run.py` + `log_view.py` (~800
lines) re-implement features Lima 2.x provides natively:

- **Template composition** — `base:` accepts multiple templates; provision
  lists are merged with bases prepended. Profile stacking is built in.
- **Per-boot provisioning** — provision scripts run via cloud-init
  `scripts_per_boot` on *every* boot, so re-provisioning needs no custom
  machinery.
- **Declarative file placement** — `mode: data` entries write dotfiles each
  boot, with `overwrite: false` for write-once files, and guest templating
  (`{{.Param.*}}`) for host-supplied values.
- **Relative `file:` refs** — provision scripts live as plain `.sh` files
  next to the templates; no pushing into the VM.
- **Automatic port forwarding** — Lima forwards listening guest ports to
  127.0.0.1; the hardcoded ranges are unnecessary.

## Architecture

### Repo layout

```
machine/
├── bin/machine                  # single-file Python CLI, ~300-400 lines
├── templates/
│   ├── base.yaml                # whole base VM, declaratively
│   ├── cypress.yaml             # profile = template fragment
│   └── supabase-fly.yaml
├── provision/
│   ├── base.sh                  # apt repos+packages, docker, node, gh, claude
│   ├── cypress.sh
│   └── supabase-fly.sh
├── files/                       # dotfiles, referenced as mode:data entries
├── projects.toml(.example)      # user config — format unchanged
├── Formula/machine.rb           # tap formula stays
├── completions/                 # regenerated for the smaller command set
├── tests/                       # unit tests shrink; smoke tests survive
└── docs/                        # site stays, content updated
```

### templates/base.yaml

Carries everything today's `lima.yaml` has (vz, `mounts: []`, agent
forwarding, no host pubkeys) **plus** what `push_files_to_vm` +
`run.py` did:

- `provision:` entries referencing `../provision/base.sh` (idempotent bash:
  apt repos for docker/gh/nodesource, apt packages, corepack, npm globals,
  claude installer, claude plugins config, default shell via
  `{{.Param.shell}}`)
- `mode: data` entries for zshrc, fish config, direnvrc, gitconfig,
  allowed_signers, known_hosts (`overwrite: false` so user-appended entries
  survive; the old append-merge logic is dropped)
- gitconfig/allowed_signers use `{{.Param.gitName}}`, `{{.Param.gitEmail}}`,
  `{{.Param.signingKey}}` — replaces host-side template rendering
- `param:` declarations with defaults (`shell: zsh`)

### Profile templates

`templates/<profile>.yaml` contain only their own `provision:` (+ optional
`mode: data` / apt bits). No `base:` inside them — composition happens in
the generated per-project template. Only `cypress` and `supabase-fly`
survive; `go`, `rust`, `python` are deleted (recreate on demand — they're
~20 lines each).

### `machine up <project>` flow

1. Read `projects.toml` → profiles, repos, shell.
2. Write `.build/<project>/lima.yaml`:
   ```yaml
   base:
     - /abs/path/templates/base.yaml
     - /abs/path/templates/cypress.yaml   # per selected profile
   ```
   When a fresh baked image exists, prepend it as the highest-priority
   `images:` entry (same mechanism as today).
3. `limactl create --tty=false --name=<project> --set ...` (git identity,
   signing key, shell) + `limactl start`. Lima merges templates, runs
   provisioning in order, writes dotfiles. Output is limactl's own; the
   provision log is cloud-init's log inside the VM.
4. Clone repos via `limactl shell` (needs the forwarded SSH agent, so it
   stays in the CLI). Pre-flight reachability check kept.

### Provisioning semantics

Scripts re-run on **every boot**. They are written idempotent (apt is;
installers guard with `command -v`). On baked images re-runs fast-skip.
Consequences:

- `update` command is deleted: *update = `machine down && machine up`*.
- No guard files, no re-run plumbing.

### CLI surface (single-file Python, stdlib only)

| Command | Implementation |
|---|---|
| `up` | render template → `limactl create`/`start` → clone repos |
| `down` / `destroy` | `limactl stop` / `stop -f` + `delete` |
| `ssh` / `claude` / `run` | `limactl shell` with cwd at primary repo |
| `list` | thin `limactl list` passthrough annotated with project names |
| `secrets` | unchanged — 1Password → VM tmpfs logic moves over as-is |
| `bake` | unchanged mechanism; hash over `templates/* + provision/* + files/*` |
| `init` | unchanged (copies example config) |
| `doctor` | minimal preflight: SSH agent, git config, signing key (~40 lines) |

Dropped: `ps`, `status`, `validate`, `update`, `config add-project`, all
`--json` flags, `--plain`/`--verbose` renderer modes.

### bake

Same disk-export trick: create `machine-base` from `templates/base.yaml`
alone, wait for provisioning, stop, `cp -c` the disk to the golden image,
stamp with the content hash. `up` prepends `file://` image when fresh.

## Deletions

- `gui/` (2.1 GB), `Casks/machine-gui.rb`, DMG release workflow,
  `.pnpm-store/` at repo root, GUI specs/plans under `docs/superpowers/`
- `provision/run.py`, `provision/log_view.py`, `provision.toml`,
  `profiles/*.toml`, `schemas/`
- In `bin/machine`: `push_files_to_vm`, `push_file`, `render_git_templates`,
  `run_provision_in_vm`, `spawn_provisioner`, renderer helpers, ps/list/
  doctor polish (idle detection, port probing, rich tables), JSON builders
- Unit tests for deleted code (`test_provision*`, `test_log_view`,
  `test_ps*`, `test_list_json`, `test_doctor_json`, `test_cmd_up_renderer`,
  `test_config_add_project`)

## Kept

- `projects.toml` format and location rules (dev mode vs `MACHINE_CONFIG_DIR`)
- Security posture: `mounts: []`, agent-forward only, strict host key
  checking via pre-seeded known_hosts, signed git
- Homebrew formula + tap runbook, completions, docs site (content updated)
- Smoke tests (`smoke-boot`, `smoke-docker`, `smoke-node`, `smoke-clis`,
  `smoke-agents`, `smoke-git-sign`, `smoke-cypress`, `smoke-claude-plugins`,
  `smoke-port-forward`) — they assert in-VM outcomes, not implementation.
  `smoke-port-forward` is updated for auto-forwarding semantics.

## Risks / open verifications

- **Lima version floor**: multi-base `base:` lists and `mode: data`
  templating require a recent Lima (local: 2.1.1). The formula must pin a
  minimum Lima version.
- **Param plumbing**: `--set` flag shape for params should be verified
  against `limactl create --help` during implementation (template `param:` +
  CLI override).
- **Baked image + per-boot provisioning**: verify provision scripts re-run
  cleanly on a cloned disk (cloud-init instance-id changes; scripts are
  idempotent so this should be safe).
- **Auto port-forward**: confirm Cypress/dev-server flows work without the
  explicit ranges before deleting them.

## Net effect

~3,200 lines of Python/DSL → ~350 lines of Python + ~150 lines of YAML +
~120 lines of bash. One engine (Lima), one config (projects.toml), one
wrapper.
