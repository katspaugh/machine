# Robustness fixes and unit tests for I/O paths

Three small bugs-in-waiting in `bin/machine` get fixed, and the fixes get
locked in with unit tests that mock the subprocess boundary. No success-path
behavior changes.

## 1. Surface deps-install failures in the `up` summary

**Problem.** When `yarn/pnpm/npm install` fails after a clone, `clone_repo`
prints one stderr line (`bin/machine:446`) and `cmd_up` still finishes with
`✓ {name} ready`. The user reasonably assumes the VM is fully set up.

**Fix.** `clone_repo` returns a warning string on deps failure (`None`
otherwise). `cmd_up` collects the warnings from all clones and ends with:

- No warnings: `✓ {name} ready — run 'machine ssh {name}' to log in.`
  (unchanged)
- Warnings: `⚠ {name} ready with warnings:` followed by one indented line
  per warning, e.g. `deps install failed for <repo> — re-run inside the VM`.

Exit code stays 0 in both cases: the VM is usable and a transient registry
hiccup should not fail an otherwise healthy `up`.

## 2. Resolve the guest workdir from the guest, not host `$USER`

**Problem.** `_primary_repo_workdir` runs a `[ -d ... ]` existence check in
the guest, then *constructs* the path as `/home/{os.environ["USER"]}.linux/...`
(`bin/machine:509`). This raises a raw `KeyError` when `USER` is unset and
silently produces a wrong path when the host username differs from the Lima
guest user.

**Fix.** Replace the existence check and the path construction with a single
guest call: `bash -lc 'cd "$HOME/code/<repo>" && pwd'` with captured output.
Exit 0 → return the printed path verbatim; nonzero → return `None`. Same
number of `limactl` round-trips, no host-environment assumption.

## 3. Distinguish "VM unreachable" from "nothing found" in `secrets`

**Problem.** `cmd_secrets` ignores the return code of the `find` probe
(`bin/machine:671-675`). If the VM is stopped or missing, `limactl shell`
fails, stdout is empty, and the user gets the misleading "no repos with
`use op_env` .envrc found". `cmd_secrets_clear --repo` has the same flaw:
its `ls ... || true` probe masks limactl failure and reports "no .envrc".

**Fix.** Check the probe's return code in both places. On failure:
`die(f"cannot reach VM '{name}' — is it running? (machine up {name})")`.
The existing "nothing found" messages remain for the case where the probe
succeeds with empty output.

## 4. Unit tests via `unittest.mock` at the subprocess boundary

The risky I/O code is currently untested. Tests go in the existing
`tests/unit/test_machine.py` style, mocking `subprocess.run`, `run`, and
`lima_shell` with `unittest.mock.patch` — no new dependencies (stdlib-only
ethos holds) and no production refactor (a runner abstraction or a fake
`limactl` shim were considered and rejected as disproportionate).

New cases:

- `clone_repo`: deps failure → returns warning; success → returns `None`.
- `cmd_up`: warning present → `⚠ ... ready with warnings` summary, exit 0;
  no warnings → unchanged `✓` summary.
- `_primary_repo_workdir`: guest exit 0 → returns guest-printed path;
  nonzero → `None`; no `USER` lookup anywhere.
- `cmd_secrets`: probe failure → dies with "cannot reach VM"; probe success
  with empty output → existing "nothing found" message and exit 1.
- `cmd_secrets_clear --repo`: probe failure → dies with "cannot reach VM".
- `sync_one_env`: `op` failure → returns `False`, nothing sent to the VM;
  success → secret material is piped via stdin (never argv).

## Out of scope

- Running the VM smoke tests in CI (needs a virtualization-capable runner —
  separate discussion).
- Any refactor of `bin/machine`'s process-execution seams.
