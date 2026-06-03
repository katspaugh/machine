# Robustness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three silent-failure paths in `bin/machine` (deps-install failures hidden by `✓ ready`, host-`$USER` guest-path assumption, secrets commands conflating "VM unreachable" with "nothing found") and lock each in with unit tests that mock the subprocess boundary.

**Architecture:** `bin/machine` is a single-file, stdlib-only Python CLI; all VM interaction funnels through `run()`, `lima_shell()`, and direct `subprocess.run()` calls. Each fix changes only failure-path behavior. Tests load the module via the existing `load_machine()` helper and patch `lima_shell`/`run`/`subprocess.run` attributes with `unittest.mock` — no new dependencies, no production refactor.

**Tech Stack:** Python 3.12 stdlib (`unittest`, `unittest.mock`, `subprocess`), bash test runner `tests/unit.sh`.

**Spec:** `docs/superpowers/specs/2026-06-03-robustness-fixes-design.md`

**Run all tests:** `./tests/unit.sh` (from repo root). Run one test: `python3 -m unittest discover -s tests/unit -t . -p 'test_machine.py' -k <pattern> -v`

---

### Task 1: Test scaffolding — shared base class and fake-process helper

**Files:**
- Modify: `tests/unit/test_machine.py`

The new tests need the same module-loading `setUp` as `TestHelpers`, plus a
`CompletedProcess` factory. Extract a base class so the three new test classes
don't copy it.

- [ ] **Step 1: Add imports, `proc()` helper, and `_MachineTestCase` base; re-parent `TestHelpers`**

In `tests/unit/test_machine.py`, replace the import block (lines 2–7) with:

```python
import argparse
import contextlib
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock
```

Below `load_machine()`, add:

```python
def proc(rc: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    """A fake CompletedProcess for mocked run()/lima_shell() calls."""
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


class _MachineTestCase(unittest.TestCase):
    """Loads bin/machine fresh against a temp projects.toml."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        projects = Path(self.tmp.name) / "projects.toml"
        projects.write_text(
            'default_profile = "cypress"\n'
            "[blog]\n"
            'repos = ["git@github.com:me/blog.git"]\n'
            "[wallet]\n"
            'profiles = ["cypress", "supabase-fly"]\n'
            'shell = "fish"\n'
            'repos = ["git@github.com:me/a.git", "git@github.com:me/b.git"]\n'
            "[bare]\n"
            "profiles = []\n"
            'repos = []\n'
        )
        self.m = load_machine({
            "PROJECTS_FILE": str(projects),
            "MACHINE_STATE_DIR": str(Path(self.tmp.name) / "state"),
        })

    def tearDown(self):
        self.tmp.cleanup()
```

Then change `TestHelpers` to inherit from it and delete its now-duplicate
`setUp`/`tearDown` (its eight test methods stay untouched):

```python
class TestHelpers(_MachineTestCase):
    def test_repo_basename(self):
        ...
```

- [ ] **Step 2: Run the full suite to verify the refactor is behavior-neutral**

Run: `./tests/unit.sh`
Expected: `Ran 8 tests ... OK` (same 8 tests as before)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_machine.py
git commit -m "Extract _MachineTestCase base and proc() helper for I/O tests"
```

---

### Task 2: `clone_repo` returns a warning; `cmd_up` prints a `⚠` summary

**Files:**
- Modify: `bin/machine:414-481` (`clone_repo`, `cmd_up`)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_machine.py`:

```python
class TestCloneWarnings(_MachineTestCase):
    def test_clone_repo_returns_warning_on_deps_failure(self):
        # 1st lima_shell: repo-present probe (rc 1 = absent)
        # run(): git clone (ok)
        # 2nd lima_shell: deps install (rc 1 = failed)
        with mock.patch.object(self.m, "lima_shell",
                               side_effect=[proc(1), proc(1)]) as sh, \
             mock.patch.object(self.m, "run", return_value=proc(0)):
            warning = self.m.clone_repo("blog", "git@github.com:me/blog.git")
        self.assertEqual(warning, "deps install failed for blog — re-run inside the VM")
        self.assertEqual(sh.call_count, 2)

    def test_clone_repo_returns_none_on_success(self):
        with mock.patch.object(self.m, "lima_shell",
                               side_effect=[proc(1), proc(0)]), \
             mock.patch.object(self.m, "run", return_value=proc(0)):
            self.assertIsNone(self.m.clone_repo("blog", "git@github.com:me/blog.git"))

    def test_clone_repo_returns_none_when_already_present(self):
        with mock.patch.object(self.m, "lima_shell", return_value=proc(0)), \
             mock.patch.object(self.m, "run") as run_mock:
            self.assertIsNone(self.m.clone_repo("blog", "git@github.com:me/blog.git"))
        run_mock.assert_not_called()

    def _run_up(self, clone_result):
        """Drive cmd_up with all I/O mocked; return captured stdout."""
        out = io.StringIO()
        with mock.patch.object(self.m, "close_lima_ssh_master"), \
             mock.patch.object(self.m, "verify_repos_reachable"), \
             mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch.object(self.m, "run", return_value=proc(0)), \
             mock.patch.object(self.m, "clone_repo", return_value=clone_result), \
             contextlib.redirect_stdout(out):
            rc = self.m.cmd_up(argparse.Namespace(project="blog"))
        return rc, out.getvalue()

    def test_cmd_up_prints_check_summary_without_warnings(self):
        rc, out = self._run_up(None)
        self.assertEqual(rc, 0)
        self.assertIn("✓ blog ready", out)
        self.assertNotIn("⚠", out)

    def test_cmd_up_prints_warning_summary_and_exits_zero(self):
        rc, out = self._run_up("deps install failed for blog — re-run inside the VM")
        self.assertEqual(rc, 0)
        self.assertIn("⚠ blog ready with warnings:", out)
        self.assertIn("  deps install failed for blog — re-run inside the VM", out)
        self.assertNotIn("✓", out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest discover -s tests/unit -t . -p 'test_machine.py' -k TestCloneWarnings -v`
Expected: FAIL — `clone_repo` currently returns `None` always but the warning
test asserts a string, and `cmd_up` never prints `⚠`.

- [ ] **Step 3: Implement**

In `bin/machine`, change `clone_repo` (lines 414–446):

```python
def clone_repo(vm: str, url: str) -> str | None:
    """Clone one repo into ~/code/<basename>/ inside the VM. Idempotent.
    JS dependency install is best-effort; returns a warning string when it
    fails (None otherwise) so cmd_up can surface it in the summary."""
    repo_name = repo_basename(url)
    rc = lima_shell(
        vm,
        ["bash", "-lc", f'[ -d "$HOME/code/{shlex.quote(repo_name)}/.git" ]'],
        stdin=subprocess.DEVNULL,
    ).returncode
    if rc == 0:
        print(f"[clone] {repo_name}: already present")
        return None
    print(f"[clone] {repo_name}")
    run(["limactl", "shell", vm, "--",
         "env",
         "GIT_SSH_COMMAND=ssh -o StrictHostKeyChecking=accept-new -o UpdateHostKeys=no",
         "bash", "-lc",
         f'mkdir -p "$HOME/code" && cd "$HOME/code" && '
         f'git clone --recurse-submodules -- {shlex.quote(url)}'])
    deps_script = (
        f'cd "$HOME/code/{shlex.quote(repo_name)}" 2>/dev/null || exit 0\n'
        '[ -f package.json ] || exit 0\n'
        'if grep -q \'"packageManager":[[:space:]]*"yarn\' package.json 2>/dev/null; then\n'
        '  echo "[deps] yarn install"; yarn install\n'
        'elif grep -q \'"packageManager":[[:space:]]*"pnpm\' package.json 2>/dev/null; then\n'
        '  echo "[deps] pnpm install"; pnpm install\n'
        'else\n'
        '  echo "[deps] npm install"; npm install\n'
        'fi'
    )
    deps_rc = lima_shell(vm, ["bash", "-lc", deps_script]).returncode
    if deps_rc != 0:
        print(f"[deps] {repo_name}: install failed (continuing)", file=sys.stderr)
        return f"deps install failed for {repo_name} — re-run inside the VM"
    return None
```

And the tail of `cmd_up` (lines 478–481):

```python
    warnings = []
    for url in urls:
        warning = clone_repo(name, url)
        if warning:
            warnings.append(warning)
    if warnings:
        print(f"⚠ {name} ready with warnings:")
        for warning in warnings:
            print(f"  {warning}")
    else:
        print(f"✓ {name} ready — run 'machine ssh {name}' to log in.")
    return 0
```

- [ ] **Step 4: Run the full suite**

Run: `./tests/unit.sh`
Expected: `Ran 13 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add bin/machine tests/unit/test_machine.py
git commit -m "Surface deps-install failures in the machine up summary"
```

---

### Task 3: `_primary_repo_workdir` asks the guest for its path

**Files:**
- Modify: `bin/machine:492-510` (`_primary_repo_workdir`)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_machine.py`:

```python
class TestPrimaryRepoWorkdir(_MachineTestCase):
    def test_returns_guest_printed_path(self):
        with mock.patch.object(
            self.m, "lima_shell",
            return_value=proc(0, stdout="/home/other.linux/code/blog\n"),
        ) as sh:
            self.assertEqual(self.m._primary_repo_workdir("blog"),
                             "/home/other.linux/code/blog")
        guest_cmd = sh.call_args.args[1]
        self.assertIn('cd "$HOME/code/blog" && pwd', guest_cmd[-1])

    def test_returns_none_when_repo_dir_missing(self):
        with mock.patch.object(self.m, "lima_shell", return_value=proc(1)):
            self.assertIsNone(self.m._primary_repo_workdir("blog"))

    def test_does_not_read_host_user_env(self):
        # Regression: used to KeyError on missing USER and to fabricate
        # /home/$USER.linux/... from the host environment.
        with mock.patch.dict(self.m.os.environ, {}, clear=True), \
             mock.patch.object(
                 self.m, "lima_shell",
                 return_value=proc(0, stdout="/home/whoever/code/blog\n"),
             ):
            self.assertEqual(self.m._primary_repo_workdir("blog"),
                             "/home/whoever/code/blog")

    def test_returns_none_for_project_without_repos(self):
        with mock.patch.object(self.m, "lima_shell") as sh:
            self.assertIsNone(self.m._primary_repo_workdir("bare"))
        sh.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest discover -s tests/unit -t . -p 'test_machine.py' -k TestPrimaryRepoWorkdir -v`
Expected: FAIL — current code returns `/home/<host-user>.linux/...` built from
`os.environ["USER"]`, so the guest-path and no-USER tests break.

- [ ] **Step 3: Implement**

Replace the body of `_primary_repo_workdir` after the `repo_name = ...` line
(lines 501–510):

```python
    # Ask the guest for the real path instead of fabricating it from the
    # host $USER (host and guest usernames need not match).
    out = lima_shell(
        name,
        ["bash", "-lc", f'cd "$HOME/code/{shlex.quote(repo_name)}" && pwd'],
        stdin=subprocess.DEVNULL,
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None
```

- [ ] **Step 4: Run the full suite**

Run: `./tests/unit.sh`
Expected: `Ran 17 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add bin/machine tests/unit/test_machine.py
git commit -m "Resolve VM workdir from the guest instead of host USER"
```

---

### Task 4: secrets commands die when the VM is unreachable

**Files:**
- Modify: `bin/machine:665-705` (`cmd_secrets`), `bin/machine:708-747` (`cmd_secrets_clear`)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_machine.py`. Note: `cmd_secrets` and
`cmd_secrets_clear` call `subprocess.run` directly (not `lima_shell`), so the
tests patch `self.m.subprocess.run`, and `shutil.which` for the `op` check.

```python
class TestSecretsReachability(_MachineTestCase):
    def _secrets_args(self, **kw):
        defaults = dict(project="blog", repo=None, clear=False)
        defaults.update(kw)
        return argparse.Namespace(**defaults)

    def test_cmd_secrets_dies_when_vm_unreachable(self):
        with mock.patch.object(self.m.shutil, "which", return_value="/usr/bin/op"), \
             mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(255, stderr="ssh: connect failed")), \
             self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.cmd_secrets(self._secrets_args())
        self.assertIn("cannot reach VM 'blog'", err.getvalue())
        self.assertIn("machine up blog", err.getvalue())

    def test_cmd_secrets_keeps_nothing_found_message(self):
        # Probe succeeds but finds no .envrc files: not an error, exit 1
        # with the existing hint.
        with mock.patch.object(self.m.shutil, "which", return_value="/usr/bin/op"), \
             mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(0, stdout="")), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            rc = self.m.cmd_secrets(self._secrets_args())
        self.assertEqual(rc, 1)
        self.assertIn("no repos with 'use op_env'", err.getvalue())

    def test_cmd_secrets_clear_repo_dies_when_vm_unreachable(self):
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(255, stderr="ssh: connect failed")), \
             self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.cmd_secrets_clear(self._secrets_args(repo="blog", clear=True))
        self.assertIn("cannot reach VM 'blog'", err.getvalue())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest discover -s tests/unit -t . -p 'test_machine.py' -k TestSecretsReachability -v`
Expected: the two `unreachable` tests FAIL (no SystemExit; the misleading
"nothing found" path runs instead). The `nothing_found` test may already pass.

- [ ] **Step 3: Implement**

In `cmd_secrets`, after the `find_envrcs = subprocess.run(...)` call
(line 671–675), add:

```python
    if find_envrcs.returncode != 0:
        die(f"cannot reach VM '{name}' — is it running? (machine up {name})")
```

In `cmd_secrets_clear`, replace the `envrc_path = subprocess.run(...)` block
(lines 725–729) with:

```python
    probe = subprocess.run(
        ["limactl", "shell", name, "--", "bash", "-lc",
         f"ls $HOME/code/{shlex.quote(args.repo)}/.envrc 2>/dev/null || true"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        die(f"cannot reach VM '{name}' — is it running? (machine up {name})")
    envrc_path = probe.stdout.strip()
```

- [ ] **Step 4: Run the full suite**

Run: `./tests/unit.sh`
Expected: `Ran 20 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add bin/machine tests/unit/test_machine.py
git commit -m "Fail secrets commands clearly when the VM is unreachable"
```

---

### Task 5: lock in `sync_one_env` behavior (test-only)

**Files:**
- Test: `tests/unit/test_machine.py`

No production change — these tests pin down the existing contract: `op`
failure aborts without touching the VM; on success the secret material travels
via stdin, never argv.

- [ ] **Step 1: Write the tests**

Append to `tests/unit/test_machine.py`:

```python
class TestSyncOneEnv(_MachineTestCase):
    def test_op_failure_returns_false_and_skips_vm(self):
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(1, stderr="not signed in")) as sp, \
             contextlib.redirect_stderr(io.StringIO()) as err:
            ok = self.m.sync_one_env("blog", "abc123", "blog")
        self.assertFalse(ok)
        self.assertEqual(sp.call_count, 1)  # op only; limactl never invoked
        self.assertIn("not signed in", err.getvalue())

    def test_success_pipes_secret_via_stdin_not_argv(self):
        secret = "TOKEN=hunter2\n"
        with mock.patch.object(self.m.subprocess, "run",
                               side_effect=[proc(0, stdout=secret), proc(0)]) as sp:
            ok = self.m.sync_one_env("blog", "abc123", "blog")
        self.assertTrue(ok)
        push = sp.call_args_list[1]
        self.assertEqual(push.kwargs.get("input"), secret)
        self.assertNotIn(secret, " ".join(push.args[0]))
        self.assertEqual(push.args[0][:3], ["limactl", "shell", "blog"])
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m unittest discover -s tests/unit -t . -p 'test_machine.py' -k TestSyncOneEnv -v`
Expected: PASS (characterization tests of existing behavior). If either fails,
stop and investigate — that means the contract is not what the spec assumed.

- [ ] **Step 3: Run the full suite and lint**

Run: `./tests/unit.sh && ./tests/lint.sh`
Expected: `Ran 22 tests ... OK`; lint clean.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_machine.py
git commit -m "Add characterization tests for sync_one_env"
```
