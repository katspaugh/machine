# tmux-backed `machine claude` Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `machine claude <p>` runs claude inside a tmux session in the VM so dropped SSH connections (or deliberate detach) leave the agent running, and re-running the command reattaches.

**Architecture:** A one-line change of shape in `cmd_claude` (`bin/machine`): instead of `exec claude`, exec `tmux new-session -A -s claude claude` inside the existing `bash -lic` login wrapper. `-A` gives create-or-attach semantics; claude as the session command means the session dies when claude exits. `tmux` is already in the base apt packages (`provision/base.sh:43`) — no provisioning change needed.

**Tech Stack:** Python 3 (`bin/machine` host CLI), bash smoke tests run via `limactl shell`, tmux ≥ 3.x (Ubuntu base image).

**Spec:** `docs/superpowers/specs/2026-06-03-tmux-claude-sessions-design.md`

---

### Task 1: tmux wrapper in `cmd_claude`

The spec calls for no unit test here (thin exec wrapper — asserting on the argv string would test the implementation, not behavior; real behavior is covered by Task 2's smoke test and Task 3's manual check). So this task is implement → lint/unit suite → commit.

**Files:**
- Modify: `bin/machine:562-571` (`cmd_claude`)

- [ ] **Step 1: Rewrite `cmd_claude`**

Replace the current function:

```python
def cmd_claude(args: argparse.Namespace) -> int:
    name = args.project
    workdir = _primary_repo_workdir(name)
    cmd = ["limactl", "shell"]
    if workdir:
        cmd += ["--workdir", workdir]
    # Login+interactive bash so /etc/profile.d/* sets PATH the same way
    # `machine ssh` users see, then hand the tty to claude.
    cmd += [name, "bash", "-lic", "exec claude"]
    os.execvp("limactl", cmd)
```

with:

```python
def cmd_claude(args: argparse.Namespace) -> int:
    name = args.project
    workdir = _primary_repo_workdir(name)
    cmd = ["limactl", "shell"]
    if workdir:
        cmd += ["--workdir", workdir]
    # Login+interactive bash so /etc/profile.d/* sets PATH the same way
    # `machine ssh` users see, then hand the tty to tmux. `new-session -A`
    # creates the session on first run and reattaches on subsequent runs
    # (a dropped SSH connection leaves claude running). claude is the
    # session command, so the session ends when claude exits.
    cmd += [name, "bash", "-lic", "exec tmux new-session -A -s claude claude"]
    print(
        f"detach: ctrl-b d — claude keeps running; reattach: machine claude {name}",
        file=sys.stderr,
    )
    os.execvp("limactl", cmd)
```

(`sys` is already imported at the top of `bin/machine`; verify, don't re-import.)

- [ ] **Step 2: Run the host test suite**

Run: `bash tests/lint.sh && bash tests/unit.sh`
Expected: both pass (no behavior is unit-covered here; this guards against syntax/lint regressions).

- [ ] **Step 3: Commit**

```bash
git add bin/machine
git commit -m "Run machine claude inside a tmux session (create-or-reattach)"
```

---

### Task 2: Smoke test for tmux session lifecycle

Tests that the in-VM premise holds: tmux is installed by base provisioning, a detached session survives the SSH connection that created it, and a killed session is gone. Uses a benign `sleep` command and a test-only session name so it never collides with a user's live `claude` session on the same VM.

`tests/run-all.sh` globs `smoke-*.sh`, so the new file is picked up automatically.

**Files:**
- Create: `tests/smoke-tmux.sh`

- [ ] **Step 1: Write the smoke test**

```bash
#!/usr/bin/env bash
# Smoke: tmux is provisioned and detached sessions survive the SSH
# connection that created them (the mechanism behind `machine claude`).
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

SESSION="machine-smoke-tmux"

# tmux present (provision/base.sh apt list).
limactl shell "$NAME" -- bash -lc 'command -v tmux >/dev/null' \
  || { echo "tmux not installed"; exit 1; }

# Clean slate, then create a detached session the way cmd_claude does
# (new-session with a command), over a connection that immediately closes.
limactl shell "$NAME" -- bash -lc "tmux kill-session -t $SESSION 2>/dev/null; true"
limactl shell "$NAME" -- bash -lc "tmux new-session -d -s $SESSION 'sleep 300'"

# The session outlives the connection that created it.
limactl shell "$NAME" -- bash -lc "tmux has-session -t $SESSION" \
  || { echo "detached session did not survive"; exit 1; }

# Killing the session removes it (mirrors claude exiting).
limactl shell "$NAME" -- bash -lc "tmux kill-session -t $SESSION"
if limactl shell "$NAME" -- bash -lc "tmux has-session -t $SESSION 2>/dev/null"; then
  echo "session still present after kill"; exit 1
fi

echo "tmux OK"
```

- [ ] **Step 2: Make it executable and lint**

Run: `chmod +x tests/smoke-tmux.sh && bash tests/lint.sh`
Expected: lint passes.

- [ ] **Step 3: Run the smoke against a provisioned VM**

Run: `MACHINE_NAME=wallet bash tests/smoke-tmux.sh` (any running provisioned VM works; `machine up wallet` first if stopped)
Expected output ends with: `tmux OK`

- [ ] **Step 4: Commit**

```bash
git add tests/smoke-tmux.sh
git commit -m "Add tmux session-lifecycle smoke test"
```

---

### Task 3: Docs + manual end-to-end check

**Files:**
- Modify: `README.md:159` (Commands table, `machine claude` row)
- Modify: `docs/docs/index.html:171` (same row in the site's command table)

- [ ] **Step 1: Update the README command row**

Replace line 159:

```markdown
| `machine claude <p>` | Open an SSH session and launch `claude` straight away (cwd = `~/code/<primary-repo>`). Exiting `claude` ends the session. |
```

with:

```markdown
| `machine claude <p>` | Launch `claude` in a tmux session in the VM (cwd = `~/code/<primary-repo>`). Detach with `ctrl-b d` — claude keeps running; re-run to reattach. Exiting `claude` ends the session. |
```

- [ ] **Step 2: Update the site command row**

Replace line 171 of `docs/docs/index.html`:

```html
              <tr><td>machine claude &lt;p&gt;</td><td class="desc">Open an SSH session and launch <code>claude</code> straight away, cwd = <code>~/code/&lt;primary-repo&gt;</code>.</td></tr>
```

with:

```html
              <tr><td>machine claude &lt;p&gt;</td><td class="desc">Launch <code>claude</code> in a tmux session, cwd = <code>~/code/&lt;primary-repo&gt;</code>. Detach with <code>ctrl-b d</code> — claude keeps running; re-run to reattach.</td></tr>
```

- [ ] **Step 3: Update the argparse help string**

`bin/machine:812` currently reads:

```python
    sub.add_parser("claude", help="Open an SSH session and launch `claude`").add_argument("project", nargs="?", default="default")
```

Replace with:

```python
    sub.add_parser("claude", help="Launch `claude` in a tmux session (re-run to reattach)").add_argument("project", nargs="?", default="default")
```

- [ ] **Step 4: Manual end-to-end check**

With a running VM (e.g. `machine up wallet`):

1. `machine claude wallet` → hint line prints, claude starts in tmux (status bar at the bottom).
2. Press `ctrl-b d` → connection closes, back on the host.
3. `machine run wallet tmux ls` → shows `claude: 1 windows …`.
4. `machine claude wallet` → reattaches to the same claude session.
5. Exit claude (`/exit` or ctrl-d) → session ends, connection closes.
6. `machine run wallet tmux ls` → `no server running …` (exit code ≠ 0 is fine).

Expected: all six observations as described.

- [ ] **Step 5: Run the full host suite once more**

Run: `bash tests/lint.sh && bash tests/unit.sh`
Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/docs/index.html bin/machine
git commit -m "Document tmux-backed machine claude sessions"
```
