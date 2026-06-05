# Plan: `machine ssh` agent self-heal + remove `machine tab`

Date: 2026-06-05
Branch: `ssh-agent-selfheal-drop-tab`

## Background

`machine ssh <vm>` can land in a VM whose forwarded SSH agent has no keys, so
commit signing (1Password SSH key) fails. Root cause: Lima's `ssh.config` uses
`ControlMaster auto` + `ControlPersist yes`, so agent forwarding is pinned at the
moment the persistent master is first created. If that master was created while
`SSH_AUTH_SOCK` pointed at the empty macOS Keychain agent (e.g. 1Password was
locked during `machine up`), every later `machine ssh` reuses it and forwards the
empty agent. `configure_ssh_agent()` is already correct — the gap is that nothing
re-checks a *live* master.

Separately, `machine tab` (macOS Terminal.app new-tab helper) does not work
reliably and is being removed.

Two independent tasks, two commits.

## Task 1 — Remove `machine tab` entirely

Delete every trace of the `tab` subcommand. It is the only user of
`_project_from_ps_args` and `_front_tab_tty`, so those go too.

Edits:
- `bin/machine`:
  - Remove `cmd_tab` (currently ~627-659), `_front_tab_tty` (~614-624), and
    `_project_from_ps_args` (~566-582).
  - Remove the `tab` subparser (the `sub.add_parser("tab", ...)` block, ~906-907).
  - Remove the `"tab": cmd_tab,` dispatch entry (~937).
  - Leave the `shlex` and `sys` imports — both are still used elsewhere (verify
    with grep before removing anything).
- `completions/_machine` (zsh): remove the `'tab:...'` line and `tab` from the
  `up|down|ssh|claude|tab|run|secrets|destroy)` case.
- `completions/machine.bash`: remove `tab` from the `cmds` string and from the
  project-completing case.
- `completions/machine.fish`: remove `tab` from the `cmds` list and from the
  `for c in ...` project-completing list.
- `README.md`: remove the `| machine tab [p] | ... |` table row (~179) and the
  entire `## Hotkey: new tab on the same machine (macOS)` section (~188-214).
- `tests/unit/test_machine.py`: remove `TestCmdTab` and the
  `_project_from_ps_args` test class (the tests at ~300-326 and ~418-480).
- `CHANGELOG.md`: add a `Removed` note under Unreleased: `machine tab`.

Keep the historical `docs/superpowers/{specs,plans}/2026-06-03-machine-tab*.md`
files — they are dated records of a past decision.

Verification: `python3 -m unittest discover tests/unit` (or the repo's test
runner) passes; `bin/machine --help` shows no `tab`; `grep -rn '\btab\b'` over
`bin completions README.md` returns nothing (excluding "table").

## Task 2 — `machine ssh` self-heals a stale agent master

Add to `bin/machine`, reusing existing `lima_shell()` (~156) and
`close_lima_ssh_master()` (~173):

```python
def _agent_has_keys(env=None) -> bool:
    """True if `ssh-add -l` lists >=1 identity (rc 0). rc 1 = none, rc 2 = unreachable."""
    r = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True, env=env)
    return r.returncode == 0


def _heal_stale_agent_master(name: str) -> None:
    """If a persisted Lima master forwards an empty agent while the host's
    selected agent has keys, close it so the next shell rebuilds the master with
    the live agent. No-op when there is no master or the host agent is also empty
    (so it never thrashes a legitimately keyless setup)."""
    if not (Path.home() / ".lima" / name / "ssh.sock").exists():
        return
    if not _agent_has_keys():
        return
    if lima_shell(name, ["ssh-add", "-l"],
                  capture_output=True, text=True).returncode != 0:
        close_lima_ssh_master(name)
```

`cmd_ssh` calls `_heal_stale_agent_master(name)` as its first line (before
computing workdir / building the exec). `configure_ssh_agent()` has already run
in `main()`, so the host `ssh-add -l` uses the correct `SSH_AUTH_SOCK`.

Scope: `cmd_ssh` only. `cmd_claude` is out of scope for this change.

Tests (TDD, in `tests/unit/test_machine.py`):
- `_agent_has_keys`: rc 0 → True; rc 1 → False.
- `_heal_stale_agent_master` branches (patch `Path.exists`, `_agent_has_keys`,
  `lima_shell`, `close_lima_ssh_master`):
  - no `ssh.sock` → `close_lima_ssh_master` NOT called, no VM probe.
  - host agent empty → NOT called, no VM probe.
  - master + host keys + VM probe rc 0 → NOT called.
  - master + host keys + VM probe rc != 0 → called once.

Verification: full unit suite passes.

## CHANGELOG

Under `## Unreleased`:
- Removed: `machine tab`.
- Fixed: `machine ssh` now rebuilds a stale Lima SSH master that forwards an
  empty agent, so 1Password-backed commit signing works after the agent appears.
