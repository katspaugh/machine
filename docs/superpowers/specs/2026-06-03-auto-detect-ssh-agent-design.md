# Auto-detect SSH agent (drop MACHINE_USE_1PASSWORD)

**Date:** 2026-06-03
**Status:** Approved

## Problem

`machine` forwards the host's SSH agent into the VM. Today the choice of agent
is manual: by default the macOS launchd ssh-agent (Keychain keys) is forwarded,
and users with 1Password must remember to set `MACHINE_USE_1PASSWORD=1` on
every run (or in their shell rc). Forgetting the flag silently forwards the
wrong agent.

## Goal

No flag. `machine` picks the right agent automatically:

- 1Password agent socket present → forward 1Password's agent.
- Otherwise → leave `SSH_AUTH_SOCK` untouched (macOS Keychain agent).

`MACHINE_USE_1PASSWORD` is removed entirely (no `=0` escape hatch — YAGNI).

## Design

### Agent selection (`configure_ssh_agent` in `bin/machine`)

- Resolve the 1Password socket path: `ONEPASS_SOCK` env override, else the
  default `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock`.
- If that path is a live socket, set `SSH_AUTH_SOCK` to it.
- If not, do nothing — this is the normal Keychain case, not an error. The
  current `die(...)` for a missing socket goes away.
- `ONEPASS_SOCK` is kept as the path override for non-standard installs. It
  also doubles as an escape hatch: pointing it at a non-socket path (e.g.
  `ONEPASS_SOCK=/dev/null`) forces the Keychain fallback.

### Doctor

- The "SSH agent has keys" hint drops `(or MACHINE_USE_1PASSWORD=1)`. New
  hint: `ssh-add --apple-use-keychain ~/.ssh/id_ed25519` plus a note that
  enabling 1Password's SSH agent also works.
- Doctor probes whichever agent auto-detection selected (it runs after
  `configure_ssh_agent`), so the edge case of an enabled-but-empty 1Password
  agent is still caught by the existing `ssh-add -l` check.

### Stale ControlMaster

- `close_lima_ssh_master()` stays unchanged in behavior. Its docstring is
  updated: the forwarded agent can now change between runs without any flag
  toggle (e.g. 1Password quit or launched), so closing the mux remains
  necessary to pick up the current `SSH_AUTH_SOCK`.

### Docs

- `README.md`: remove all three `MACHINE_USE_1PASSWORD` mentions; describe the
  rule — *1Password agent socket present → 1Password; otherwise macOS
  Keychain* — and keep `ONEPASS_SOCK` in the env-var table.
- `docs/docs/index.html`: same treatment for its three mentions.

## Trade-offs accepted

- A user with 1Password's SSH agent enabled but keys only in Keychain gets the
  1Password agent forwarded. Remedies: disable 1Password's agent setting, or
  `ONEPASS_SOCK=/dev/null`. `machine doctor` surfaces the symptom (agent has
  no keys).
- Socket existence, not key presence, drives selection. Probing with
  `ssh-add -l` was rejected because a locked 1Password can block `machine up`
  on a GUI unlock prompt.

## Testing

- Unit: `configure_ssh_agent` — socket present sets `SSH_AUTH_SOCK`; socket
  absent leaves the environment untouched; `ONEPASS_SOCK` override respected.
- Manual: `machine up` with 1Password running → `ssh-add -l` inside the VM
  lists 1Password keys; quit 1Password, rerun → Keychain keys. `machine
  doctor` in both states.
