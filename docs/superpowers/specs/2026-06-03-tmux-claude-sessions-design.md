# tmux-backed `machine claude` sessions

**Date:** 2026-06-03
**Status:** Approved

## Problem

`machine claude <p>` runs `claude` directly over an interactive SSH session.
If the SSH connection drops — laptop sleep, closed terminal, network blip —
the agent dies mid-task. There is no way to start a long agent run, walk
away, and come back to it.

## Goal

`machine claude <p>` runs `claude` inside a tmux session in the VM:

- The connection dropping (or the user detaching) leaves claude running.
- Re-running `machine claude <p>` reattaches to the live session instead of
  starting a second agent.
- When claude exits normally, the session ends and the SSH connection closes
  — identical UX to today for the common case.

Explicitly out of scope (YAGNI): multiple sessions per project, host
notifications, session checkpoints/diff/restore, any change to `machine ssh`.

## Design

### `cmd_claude` in `bin/machine`

Replace the direct `exec claude` with a tmux wrapper:

```
limactl shell [--workdir <primary repo>] <name> \
  bash -lic 'exec tmux new-session -A -s claude claude'
```

- `new-session -A -s claude`: create the session if absent, attach if it
  already exists. One session per project, fixed name `claude`.
- `claude` as the session command: when claude exits, tmux ends the session
  and the SSH connection closes. No lingering shells.
- The login+interactive `bash -lic` wrapper is kept so `/etc/profile.d/*`
  PATH setup applies, same as today. tmux starts claude via the user's
  default shell environment; the session inherits the workdir from
  `--workdir` (tmux uses the current directory as the session start
  directory).
- Reattach case: `--workdir` is irrelevant when attaching (tmux keeps its
  own cwd), and `-A` ignores the command argument for existing sessions, so
  the same invocation serves both paths.

Before exec'ing, print a one-line hint to stderr:

```
detach: ctrl-b d — claude keeps running; reattach: machine claude <name>
```

### Provisioning

- Add `tmux` to the base apt package list in `provision/base.sh`. It must be
  preinstalled — the feature can't depend on the user installing it.
- Re-provisioning an existing VM picks it up via the usual
  `machine down && machine up` (provision scripts re-run on every boot).

### Failure mode

If tmux is missing in an existing (not yet re-provisioned) VM, the wrapped
command fails with bash's `tmux: command not found`. Acceptable: the fix is
the documented re-provision loop, and new VMs always have it. No fallback
path to bare `claude` (it would mask the broken state).

## Docs

- `README.md`: update the `machine claude` row in the Commands table —
  mention the tmux session, detach/reattach semantics.
- `docs/docs/index.html`: same treatment if `machine claude` is described
  there.

## Testing

- Smoke (in-VM, `tests/`): after `machine claude` is started detached
  (`tmux new-session -d -s claude claude` equivalent), `tmux has-session -t
  claude` succeeds; killing the session removes it.
- Manual: `machine claude <p>` → detach with `ctrl-b d` → SSH closes, claude
  still running (`machine run <p> tmux ls`) → `machine claude <p>` reattaches
  → exit claude → session gone, connection closed.
- Unit: none — `cmd_claude` is a thin exec wrapper; asserting on the command
  string would test the implementation, not behavior.
