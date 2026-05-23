# CLI polish: wrapped provisioning output + richer `ps`

**Status:** design approved, awaiting implementation plan
**Date:** 2026-05-23

## Goals

1. `machine up <project>` should not flood the terminal with raw Lima / apt / npm / `curl|bash` output. The user should see a tidy step list with checkmarks and elapsed times. Raw output is captured to a log file and surfaced inline only when a step fails (or on `--verbose`).
2. `machine ps` should be a rich human-facing view of all VMs, showing per-VM status, uptime, CPU and memory, primary repo + branch, idle time, and the set of host ports currently forwarded and listening for each VM. One-shot (no realtime watch in this spec).

## Non-goals

- A real-time `ps --watch` mode. Explicitly deferred.
- Wrapping the renderer around `bake`, `rebuild`, or `update`. Same renderer can be reused later; this spec ships `up` only.
- Process-name labels on ports (e.g. `next-server`, `vite`). Host-side probing cannot resolve in-VM process names; we display port numbers only.
- A new runtime dependency. No `rich`, `blessed`, etc. The host CLI stays a Python 3.11+ stdlib script (`bin/machine` already advertises this in `README.md`).

## Architecture overview

Two pieces:

```
                     ┌──────────────────────────────────────┐
                     │ bin/machine (host CLI)               │
                     │                                      │
   user @ host  ───▶ │  cmd_up        cmd_ps                │
                     │     │             │                  │
                     │     ▼             ▼                  │
                     │  Renderer     ps gatherer            │
                     │  (log_view)   (parallel collectors)  │
                     └──────┬────────────┬──────────────────┘
                            │            │
                            ▼            ▼
                  ┌────────────────┐  ┌──────────────────────┐
                  │ provision/     │  │ limactl list --json  │
                  │ run.py inside  │  │ ~/.lima/<vm>/ha.*    │
                  │ the Lima VM    │  │ TCP probe 127.0.0.1  │
                  │ (emits         │  │ one shell call per   │
                  │ [step:*]       │  │ running VM (loadavg, │
                  │ markers)       │  │ free, who, branch)   │
                  └────────────────┘  └──────────────────────┘
```

## Step protocol (host ↔ in-VM provisioner)

`provision/run.py` emits a small machine-readable protocol on stdout, in addition to its existing `[provision] <name>` output. The host CLI parses these lines; everything not matching the protocol is treated as raw step output.

```
[step:start] <name>
…raw output…
[step:end] <name> ok
[step:end] <name> skip <reason>
[step:end] <name> fail <exit-code>
```

Rules:

- `<name>` is human-readable, may contain spaces, must not contain newlines.
- An `end` always matches the most recent unmatched `start` in the same process. The provisioner emits them in strict pairs; the host treats orphans defensively (close the active step with `fail` and continue).
- Lines not matching either prefix are buffered by the host as the active step's raw output.
- The protocol is additive. An older `bin/machine` that does not parse it will simply print the markers as-is — output is still legible, no breakage.
- Host-driven phases (preflight, create VM, push files, clone repos) do not flow through this protocol; the host calls the Renderer directly.

## Renderer module: `provision/log_view.py`

A new module, stdlib-only. Public surface:

```python
class Renderer:
    def __init__(self, stream, *, tty: bool, verbose: bool, log_path: Path | None): ...

    # Step lifecycle. depth controls indent; 0 = top-level, 1 = nested under "provisioning".
    def step_start(self, name: str, depth: int = 0) -> StepHandle: ...
    def step_end(self, handle: StepHandle, status: Literal["ok", "skip", "fail"], detail: str = "") -> None: ...

    # Raw subprocess output. Attributed to the currently active step.
    def raw(self, line: str) -> None: ...

    # Stream-and-parse helper: reads from a Popen's stdout, dispatches [step:*]
    # markers to step_start/end, sends everything else to raw(). Returns exit code.
    def consume(self, proc: subprocess.Popen, *, depth: int = 1) -> int: ...
```

`StepHandle` is an opaque dataclass holding the step's name, start time, depth, and a list of buffered raw lines.

### TTY mode

- ANSI cursor-up + clear-line redraws the active step every ~120 ms.
- Glyphs: `⧗` active (rotating spinner frame), `✓` ok, `↷` skip, `✗` fail.
- Completed steps remain on screen with `glyph name (duration)`.
- On `fail`, the buffered raw lines are printed below the failed step, each indented and prefixed with `  · `. No truncation — the user wants the full failure context on screen.
- On `ok` / `skip`, buffered raw lines are not printed (they live in the log file).
- If `verbose=True`, raw lines stream inline as they arrive, prefixed with `  · `, in addition to going to the log file.
- A subordinate step `step_start(... depth=1)` indents the active line by two spaces. The parent step's spinner line is held in place above; when the child ends, the parent's spinner resumes redraw on its own line.

### Plain mode (not a TTY, or `--plain`, or `MACHINE_PLAIN=1`)

- One line per `step_end` event: `[HH:MM:SS] ✓ name (duration)`.
- No cursor moves, no in-place rewrites, no spinner.
- Raw lines emit immediately on `raw()`, prefixed with the current step's indent. This matches CI-log expectations (everything is visible chronologically; no hidden state).

### Log file

- Path: `~/.machine/logs/<vm>-<iso8601>.log` (e.g. `~/.machine/logs/blog-2026-05-23T14:22:08.log`).
- Always written, in both modes. Contains every raw line plus all step events with timestamps. Format is plain text, one line per record.
- `MACHINE_PROVISION_LOG` env var, if set, overrides the default path (preserves today's behavior).
- The renderer prints the log path once at startup: `log: ~/.machine/logs/blog-2026-05-23T14:22:08.log    (--verbose to stream)`.

## `cmd_up` wiring

`bin/machine` `cmd_up` is rewritten to drive the Renderer. Pseudocode (real edits will follow this shape):

```python
def cmd_up(args):
    r = Renderer(
        sys.stdout,
        tty=sys.stdout.isatty() and not args.plain and not env_flag("MACHINE_PLAIN"),
        verbose=args.verbose or env_flag("MACHINE_VERBOSE"),
        log_path=default_log_path(name),
    )

    s = r.step_start("preflight checks"); ...; r.step_end(s, "ok")

    if not golden_fresh():
        s = r.step_start("bake base image"); bake(force=False); r.step_end(s, "ok")

    s = r.step_start(f"create VM '{name}'"); run_quiet(["limactl", "create", ...], renderer=r); r.step_end(s, "ok")
    s = r.step_start(f"start VM '{name}'");  run_quiet(["limactl", "start", name], renderer=r); r.step_end(s, "ok")

    s = r.step_start("upload provision config"); push_files_to_vm(name, profiles); r.step_end(s, "ok")

    s = r.step_start("provisioning")
    rc = r.consume(spawn_provisioner(name, profiles), depth=1)
    r.step_end(s, "ok" if rc == 0 else "fail")

    s = r.step_start("clone repos")
    for repo in repos:
        cs = r.step_start(repo_basename(repo), depth=1)
        ...clone...
        r.step_end(cs, "ok" or "skip")
    r.step_end(s, "ok")
```

Two new helpers in `bin/machine`:

- `run_quiet(cmd, *, renderer)` — `subprocess.Popen` with combined stdout+stderr piped into `renderer.raw()` line by line; returns the exit code. Replaces direct `run([...])` calls used inside `cmd_up`.
- `spawn_provisioner(name, profiles) -> subprocess.Popen` — replaces today's `run_provision_in_vm`. Builds the same `limactl shell ... sudo python3 .../run.py ...` command, but returns a `Popen` for the Renderer to drive instead of `subprocess.run`-ing it.

### Flags and env

- `--verbose` — inline raw output streaming. `MACHINE_VERBOSE=1` equivalent.
- `--plain` — force plain mode even at a TTY. `MACHINE_PLAIN=1` equivalent.
- `--dry-run` — unchanged; still surfaces through the existing provisioner `--dry-run` path.

## `machine ps`

### Behavior

- Removes the current `"ps": cmd_list` alias.
- Adds a new `cmd_ps` with the rich table layout below.
- `cmd_list` is unchanged — keeps the current terse, scriptable table.

### Output shape

```
NAME      STATUS    UPTIME   CPU   MEM         REPO              IDLE  PORTS
blog      Running   1h 12m   14%   1.8 / 4 G   blog (main)       12m   3000, 5432
wallet    Running   3h 04m    2%   0.9 / 4 G   safe-wallet (dev)  3m   5173
ledger    Stopped   —          —   —           ledger             —    —
sandbox   Running     22m     0%   0.3 / 4 G   —                 22m   —
```

- Columns: NAME, STATUS, UPTIME, CPU, MEM, REPO (with branch), IDLE, PORTS.
- For `Stopped` VMs, all dynamic columns show `—`.
- For VMs in `projects.toml` with no repos defined, REPO is `—`.
- Column widths are computed from row content (existing `cmd_list` uses fixed widths; `cmd_ps` uses dynamic widths capped at sensible maxima).
- Plain ASCII; no color in v1 (color can be a follow-up).

### Data gathering

Per `ps` invocation:

1. **Project list**: parse `projects.toml` (existing code path from `cmd_list`).
2. **VM list and core status**: one `limactl list --json` call. Used for: NAME presence, STATUS, UPTIME (derive from `created` or from `ha.pid` mtime — see below), and the per-VM directory under `~/.lima/<vm>/`.
3. **Per running VM, in parallel** (`concurrent.futures.ThreadPoolExecutor`, max workers ≈ number of running VMs):
   - **One shell call** per VM, combining cpu/mem/idle/branch:
     ```
     limactl shell <vm> -- sh -c '
       cat /proc/loadavg;
       free -b;
       who;
       cd ~/code/<primary-repo> 2>/dev/null && git rev-parse --abbrev-ref HEAD;
     '
     ```
     Output parsed host-side. `<primary-repo>` is `basename(projects.toml[vm].repos[0])`.
   - **Port discovery** (host-side, described below).
4. Render once. Exit.

Per-row gather has a hard timeout (default 3 s). If it expires, the row prints with `?` in dynamic columns rather than blocking the whole table.

### Uptime source

Two candidates: `limactl list --json`'s `created` field, and `~/.lima/<vm>/ha.pid` mtime. `created` reflects VM creation, not last start, so it overstates uptime across stop/start cycles. `ha.pid` mtime tracks the host-agent lifecycle and matches "since last start" in practice. Implementation chooses `ha.pid` mtime as the source, falling back to `created` if `ha.pid` is missing.

### Idle time

From `who` output inside the VM: the most recent login time across users. Idle = `now - max(login_time)`. If `who` is empty, idle is shown as `—` (no logged-in session; not the same as "0m"). Folded into the same shell call above to avoid a second SSH round-trip.

### CPU and memory

- **CPU**: 1-minute loadavg from `/proc/loadavg`, divided by the VM's CPU count from `limactl list --json` `.cpus`, expressed as a percent. Above 100% is shown as `>100%`.
- **MEM**: `MemAvailable` and `MemTotal` from `free -b`, formatted as `<used> / <total>` in human units (`free -b` gives bytes; format to GiB with one decimal). "Used" here is `MemTotal - MemAvailable`, which matches user intuition better than `free`'s default `used`.

### Port discovery (host-side)

For each running VM:

1. **Find the VM's currently-forwarded host→guest port map.**
   Lima logs port-forwarding events to `~/.lima/<vm>/ha.stderr.log` in the form:
   ```
   forwarding tcp from 127.0.0.1:<host>:<guest> to <vm-ip>:<guest>
   ```
   and corresponding `unforwarding` events when a guest stops listening. We read the file (whole file is small in practice; cap at the last ~2000 lines defensively) and replay the events in order, maintaining a `{(host_port, guest_port): forwarded?}` map. The final set of `forwarded=True` entries is the authoritative live map for that VM.
   The exact log line format must be confirmed against a real Lima install before implementation; if the format differs, the parser is the only thing that needs to change. Treat the parse as best-effort: any line that doesn't match is ignored.
2. **Probe liveness from the host.** For each `(host_port, guest_port)` in the map, do a `socket.socket(AF_INET, SOCK_STREAM)` with `settimeout(0.1)` and `connect_ex(("127.0.0.1", host_port))`. If it succeeds (`0`), the port is live. Otherwise, omit it.
3. **Render.** Sort live ports ascending by host port. Show host port numbers, comma-separated. No process names (host-side limitation, accepted).

### Empty / edge states

- VM running but no `ha.stderr.log` yet (just-started): PORTS column shows `—`.
- VM listed in `projects.toml` but no Lima VM created: STATUS shows `—` and dynamic columns are `—`.
- Lima VM exists but is not in `projects.toml` (created manually): row is included with REPO `—`.

## Testing

### New tests

- `tests/unit/test_log_view.py`:
  - TTY-mode renders glyphs and overwrites the active step.
  - Plain-mode emits one line per `step_end`, no cursor moves.
  - On `step_end("fail")`, buffered raw lines are flushed below the step.
  - On `step_end("ok")`, buffered raw lines are not flushed to the screen but appear in the log file.
  - Nested `step_start(depth=1)` indents correctly.
  - `consume()` parses `[step:start]` / `[step:end]` markers and forwards other lines to `raw()`.
  - Orphan `[step:end]` without a matching `start` is tolerated (logged, no crash).
- `tests/unit/test_ps.py`:
  - Canned `limactl list --json` + canned `ha.stderr.log` + canned shell-call outputs produce the expected table.
  - Port probe is monkeypatched to assert connection attempts go to the right host ports.
  - Per-VM gather timeout produces a row with `?` placeholders.
  - VM not in `projects.toml` is included with `—` in REPO.

### Existing tests

- `tests/unit/test_machine.py` already touched in the worktree state — keeps working since `cmd_list` is unchanged.
- In-VM smoke tests in `tests/smoke-*.sh` do not assert on `up` output shape — they continue to pass.

## Rollout

- The `[step:*]` markers are additive; rolling out `provision/run.py` independently of `bin/machine` is safe in both directions (old host sees markers as raw lines; new host without updated `run.py` falls back to one big "provisioning" step with no nesting).
- `MACHINE_PROVISION_LOG` is preserved as an override.
- `README.md`'s commands table gets a one-line update for `ps` ("rich live-status view of all VMs, with active ports").

## Open questions deferred to implementation plan

- Exact format of Lima's `ha.stderr.log` forwarding lines — verified at plan time against a running Lima install.
- Spinner frame characters (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` braille vs `|/-\`) — pick at plan time after a quick terminal-compat check.
- Whether to ship color in v1 — not blocking; can be added without protocol changes.
