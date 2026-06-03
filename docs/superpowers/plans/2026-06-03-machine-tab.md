# `machine tab` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `machine tab [project]` subcommand that opens a new Terminal.app tab connected to the same machine as the current tab (detected from the `limactl shell` process on the tab's tty), bindable to a hotkey via Shortcuts.app.

**Architecture:** Pure host-side change in `bin/machine`. Detection is a pure function over `ps -o args=` output (unit-testable anywhere); the macOS-only parts (reading the front tab's tty, opening the tab) are two `osascript` calls in `cmd_tab`. No state files, no guest changes.

**Tech Stack:** Python 3 stdlib (`subprocess`, `shlex`), AppleScript via `osascript`, `unittest` with mocks (existing `tests/unit/test_machine.py` harness).

**Spec:** `docs/superpowers/specs/2026-06-03-machine-tab-design.md`

**Note on environment:** Development happens on Linux; all unit tests must run without macOS. Anything touching `osascript`/`ps` is mocked; `sys.platform` is patched to `"darwin"` in tests of `cmd_tab`.

---

### Task 1: ps-args parser `_project_from_ps_args`

A pure function that scans `ps -t <tty> -o args=` output for a `limactl shell …` argv and returns the project name, or `None`.

**Files:**
- Modify: `bin/machine` (new helper next to `_primary_repo_workdir`, ~line 540)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_machine.py` (after `TestHelpers`):

```python
class TestProjectFromPsArgs(_MachineTestCase):
    def test_ssh_form_with_full_limactl_path(self):
        ps = (
            "-fish\n"
            "/opt/homebrew/bin/limactl shell --workdir /home/me.linux/code/blog blog\n"
        )
        self.assertEqual(self.m._project_from_ps_args(ps), "blog")

    def test_claude_form_with_trailing_command(self):
        ps = ("limactl shell --workdir /home/me.linux/code/a wallet "
              "bash -lic exec tmux new-session -A -s claude claude\n")
        self.assertEqual(self.m._project_from_ps_args(ps), "wallet")

    def test_bare_form(self):
        self.assertEqual(self.m._project_from_ps_args("limactl shell default\n"),
                         "default")

    def test_workdir_equals_form(self):
        ps = "limactl shell --workdir=/home/me/code/blog blog\n"
        self.assertEqual(self.m._project_from_ps_args(ps), "blog")

    def test_no_limactl_on_tty(self):
        ps = "-fish\nvim notes.md\nssh somewhere limactl shell nope\n"
        self.assertIsNone(self.m._project_from_ps_args(ps))

    def test_empty_output(self):
        self.assertIsNone(self.m._project_from_ps_args(""))
```

Note `test_no_limactl_on_tty`: the `ssh somewhere limactl shell nope` line must NOT match — argv[0] is `ssh`, not `limactl`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `tests/unit.sh 2>&1 | tail -20`
Expected: the six new tests FAIL/ERROR with `AttributeError: ... has no attribute '_project_from_ps_args'`; all pre-existing tests PASS.

- [ ] **Step 3: Implement the parser**

In `bin/machine`, after `_primary_repo_workdir` (before `def cmd_ssh`):

```python
def _project_from_ps_args(ps_output: str) -> str | None:
    """Extract the VM name from a `limactl shell ...` argv line in
    `ps -o args=` output. Matches the basename of argv[0] (ps may report
    a full path), skips flags, returns the first positional argument."""
    for line in ps_output.splitlines():
        words = line.split()
        if len(words) < 3 or Path(words[0]).name != "limactl" or words[1] != "shell":
            continue
        rest = words[2:]
        i = 0
        while i < len(rest):
            w = rest[i]
            if w.startswith("--"):
                i += 1 if "=" in w else 2  # --flag=value vs --flag value
                continue
            return w
    return None
```

(`len(words) < 3` is correct: a detectable line needs at least `limactl shell <name>`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: `OK`, zero failures.

- [ ] **Step 5: Commit**

```bash
git add bin/machine tests/unit/test_machine.py
git commit -m "Add ps-args parser for detecting the limactl shell project"
```

---

### Task 2: `cmd_tab` orchestration

**Files:**
- Modify: `bin/machine` (new `_front_tab_tty` + `cmd_tab` after `cmd_claude`, ~line 586)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_machine.py`:

```python
class TestCmdTab(_MachineTestCase):
    """cmd_tab is macOS-only; patch sys.platform and subprocess.run."""

    def _args(self, project=None):
        return argparse.Namespace(project=project)

    def test_rejects_non_macos(self):
        with mock.patch.object(self.m.sys, "platform", "linux"):
            with self.assertRaises(SystemExit):
                self.m.cmd_tab(self._args("blog"))

    def test_explicit_project_skips_detection(self):
        with mock.patch.object(self.m.sys, "platform", "darwin"), \
             mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(0)) as run_:
            rc = self.m.cmd_tab(self._args("blog"))
        self.assertEqual(rc, 0)
        # one call: the osascript that opens the tab; no tty/ps calls
        self.assertEqual(run_.call_count, 1)
        argv = run_.call_args[0][0]
        self.assertEqual(argv[:2], ["osascript", "-e"])
        self.assertIn("ssh blog", argv[2])
        self.assertIn('keystroke "t" using command down', argv[2])

    def test_detection_path(self):
        ps_out = "/opt/homebrew/bin/limactl shell --workdir /home/x/code/a wallet\n"
        calls = [
            proc(0, stdout="/dev/ttys005\n"),   # osascript: front tab tty
            proc(0, stdout=ps_out),              # ps -t ttys005
            proc(0),                             # osascript: open tab
        ]
        with mock.patch.object(self.m.sys, "platform", "darwin"), \
             mock.patch.object(self.m.subprocess, "run",
                               side_effect=calls) as run_:
            rc = self.m.cmd_tab(self._args(None))
        self.assertEqual(rc, 0)
        ps_argv = run_.call_args_list[1][0][0]
        self.assertEqual(ps_argv, ["ps", "-t", "ttys005", "-o", "args="])
        open_argv = run_.call_args_list[2][0][0]
        self.assertIn("ssh wallet", open_argv[2])

    def test_no_machine_session_dies(self):
        calls = [
            proc(0, stdout="/dev/ttys005\n"),
            proc(0, stdout="-fish\nvim notes.md\n"),
        ]
        with mock.patch.object(self.m.sys, "platform", "darwin"), \
             mock.patch.object(self.m.subprocess, "run", side_effect=calls):
            with self.assertRaises(SystemExit):
                self.m.cmd_tab(self._args(None))

    def test_terminal_not_scriptable_dies(self):
        with mock.patch.object(self.m.sys, "platform", "darwin"), \
             mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(1, stderr="not allowed")):
            with self.assertRaises(SystemExit):
                self.m.cmd_tab(self._args(None))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `tests/unit.sh 2>&1 | tail -20`
Expected: the five new tests ERROR with `AttributeError: ... has no attribute 'cmd_tab'`; everything else PASSES.

- [ ] **Step 3: Implement `_front_tab_tty` and `cmd_tab`**

In `bin/machine`, after `cmd_claude` (line ~586):

```python
def _front_tab_tty() -> str:
    """tty of the selected tab of Terminal.app's front window, e.g. /dev/ttys003."""
    out = subprocess.run(
        ["osascript", "-e",
         'tell application "Terminal" to get tty of selected tab of front window'],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        die("could not read the front Terminal tab "
            f"(is Terminal.app running?): {out.stderr.strip()}")
    return out.stdout.strip()


def cmd_tab(args: argparse.Namespace) -> int:
    if sys.platform != "darwin":
        die("machine tab drives Terminal.app and requires macOS")
    name = args.project
    if not name:
        tty = _front_tab_tty().removeprefix("/dev/")
        ps = subprocess.run(["ps", "-t", tty, "-o", "args="],
                            capture_output=True, text=True)
        name = _project_from_ps_args(ps.stdout)
        if not name:
            die("no machine session in this tab — run 'machine ssh <project>' "
                "first, or pass a project: machine tab <project>")
    # Absolute path so the new tab's login shell needs no PATH setup
    # (works for both brew installs and dev clones).
    machine_bin = str(Path(sys.argv[0]).resolve())
    cmd = f"{shlex.quote(machine_bin)} ssh {shlex.quote(name)}"
    # Escape for embedding in an AppleScript double-quoted string.
    as_cmd = cmd.replace("\\", "\\\\").replace('"', '\\"')
    # Terminal.app's AppleScript dictionary has no "make new tab"; send ⌘T
    # via System Events (first run prompts for Automation permission),
    # wait for the tab to exist, then run the command in it.
    script = (
        'tell application "Terminal" to activate\n'
        'tell application "System Events" to keystroke "t" using command down\n'
        "delay 0.3\n"
        f'tell application "Terminal" to do script "{as_cmd}" '
        "in selected tab of front window"
    )
    out = subprocess.run(["osascript", "-e", script],
                         capture_output=True, text=True)
    if out.returncode != 0:
        die(f"failed to open a new Terminal tab: {out.stderr.strip()}")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: `OK`, zero failures.

- [ ] **Step 5: Commit**

```bash
git add bin/machine tests/unit/test_machine.py
git commit -m "Add cmd_tab: open a new Terminal tab on the same machine"
```

---

### Task 3: CLI wiring + shell completions

**Files:**
- Modify: `bin/machine` (`build_parser` ~line 826, `COMMANDS` ~line 851)
- Modify: `completions/_machine`, `completions/machine.bash`, `completions/machine.fish`

- [ ] **Step 1: Register the subcommand**

In `build_parser()`, directly after the `claude` line:

```python
    sub.add_parser("tab", help="Open a new Terminal tab connected to the same machine "
                               "as the current tab (macOS)").add_argument("project", nargs="?", default=None)
```

Note `default=None`, NOT `default="default"` — an omitted project means "detect", not "the default VM".

In `COMMANDS`, after `"claude": cmd_claude,`:

```python
    "tab": cmd_tab,
```

- [ ] **Step 2: Verify wiring**

Run: `bin/machine tab 2>&1; echo "rc=$?"`
Expected (on Linux dev host): `machine: machine tab drives Terminal.app and requires macOS` and `rc=1`.

Run: `bin/machine --help 2>&1 | grep tab`
Expected: the `tab` line with its help text.

- [ ] **Step 3: Update completions (all three shells)**

`completions/_machine` — add to the `cmds` array after the `claude` entry, and add `tab` to the project-completing case:

```diff
     'claude:Open a shell and launch claude'
+    'tab:Open a new Terminal tab on the same machine'
     'run:Run a non-interactive command'
```

```diff
-    up|down|ssh|claude|run|secrets|destroy)
+    up|down|ssh|claude|tab|run|secrets|destroy)
```

`completions/machine.bash`:

```diff
-  local cmds="up down ssh claude run list destroy bake secrets init doctor"
+  local cmds="up down ssh claude tab run list destroy bake secrets init doctor"
```

```diff
-    up|down|ssh|claude|run|secrets|destroy)
+    up|down|ssh|claude|tab|run|secrets|destroy)
```

`completions/machine.fish`:

```diff
-set -l cmds up down ssh claude run list destroy bake secrets init doctor
+set -l cmds up down ssh claude tab run list destroy bake secrets init doctor
```

```diff
-for c in up down ssh claude run secrets destroy
+for c in up down ssh claude tab run secrets destroy
```

- [ ] **Step 4: Run the full unit suite + lint**

Run: `tests/unit.sh 2>&1 | tail -3 && tests/lint.sh`
Expected: `OK` and lint passes.

- [ ] **Step 5: Commit**

```bash
git add bin/machine completions/_machine completions/machine.bash completions/machine.fish
git commit -m "Wire 'machine tab' into the CLI and shell completions"
```

---

### Task 4: README documentation

**Files:**
- Modify: `README.md` (Commands table ~line 159; new section after the Commands table, before `## Repository layout` ~line 168)

- [ ] **Step 1: Add the Commands-table row**

After the `machine claude <p>` row:

```markdown
| `machine tab [p]` | macOS: open a new Terminal.app tab connected to the same machine as the current tab (detected from the tab's `limactl shell` process). Pass a project to skip detection. Bind to a hotkey via Shortcuts.app ([below](#hotkey-new-tab-on-the-same-machine-macos)). |
```

- [ ] **Step 2: Add the setup section**

Insert between the Commands table and `## Repository layout`:

```markdown
## Hotkey: new tab on the same machine (macOS)

`machine tab` looks at the frontmost Terminal.app tab, finds the
`limactl shell <project>` process on its tty, and opens a new tab
already connected to that machine. It works in tabs opened by
`machine ssh` and `machine claude` alike, and never guesses from
titles or state files — the running process is the source of truth.

To bind it to a hotkey:

1. Open **Shortcuts.app** → new shortcut → add a single **Run Shell
   Script** action with:

   ```sh
   /opt/homebrew/bin/machine tab
   ```

   (Use the path from `which machine` if you installed differently.)
2. In the shortcut's details pane (ⓘ), add a **keyboard shortcut**,
   e.g. ⌃⌘T. Shortcuts hotkeys are global — pick one that doesn't
   collide with other apps.

The first run triggers two one-time macOS permission prompts for the
invoking app (Shortcuts, or Terminal when run by hand): Automation
control of **Terminal** (to read the tab's tty and run the command)
and **System Events** (to send ⌘T — Terminal's AppleScript dictionary
has no "new tab" command). Approve both.
```

- [ ] **Step 3: Sanity-check the anchor**

Run: `grep -n "hotkey-new-tab" README.md`
Expected: the table row's `(#hotkey-new-tab-on-the-same-machine-macos)` link matches the GitHub slug of `## Hotkey: new tab on the same machine (macOS)` (lowercase, spaces→`-`, `:`/`(`/`)` dropped → `hotkey-new-tab-on-the-same-machine-macos`).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document 'machine tab' and the Shortcuts.app hotkey setup"
```

---

### Task 5: Final verification

- [ ] **Step 1: Full test suite + lint**

Run: `tests/unit.sh 2>&1 | tail -3 && tests/lint.sh`
Expected: `OK`, lint clean.

- [ ] **Step 2: Manual verification checklist (requires a macOS host — hand to the user)**

The AppleScript/GUI path cannot be exercised on the Linux dev host. Ask the user to verify on their Mac:

1. `machine ssh <project>` in a Terminal.app tab, then in another tab run `machine tab` → a new tab opens connected to `<project>` (approve the two permission prompts on first run).
2. With the connected tab frontmost, trigger the Shortcut hotkey → same result.
3. In a `machine claude` tab → hotkey opens a plain `machine ssh` tab to the same machine.
4. In a tab with no machine session, `machine tab` → clear error message, no tab opened.
5. `machine tab <project>` from any tab → connects without detection.
