# Plan 1: CLI JSON Surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the machine-readable JSON surface (`ps --json`, `list --json`, `doctor --json`) and the `config add-project` subcommand that the future Tauri GUI calls, while keeping the existing human-readable output intact.

**Architecture:** Each affected `cmd_*` function gains a `--json` flag. When set, the function collects the same data it already collects, formats it as a list/dict of raw types (seconds, bytes, percents — never em-dashes), and prints one `json.dumps` call to stdout. The default human output path is left alone, and a parallel `_*_json_*` helper does the data shaping so the existing table renderers stay untouched. `config add-project` is a new subcommand that appends a project block to `projects.toml`, validating name + repo + profile-file existence before writing.

**Tech Stack:** Python 3.12+ (stdlib only: `argparse`, `json`, `tomllib`), existing `tests/unit/` `unittest` harness, existing `_load_machine()` pattern for importing `bin/machine` as a module.

**Source-of-truth contract:** The JSON shapes defined here are consumed by Rust in plan 2 (`gui/src-tauri/src/types.rs`). Field names and types are part of the public CLI/GUI contract — do not rename without updating both sides in the same commit.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `bin/machine` | Modify | Add JSON output paths to `cmd_ps`, `cmd_list`, `cmd_doctor`. Add `cmd_config` group with `add-project` action. Add `--json` flags and the new `config` subparser. |
| `tests/unit/test_ps_json.py` | Create | Tests for `_make_ps_row_json` + `cmd_ps(--json)` round-trip. |
| `tests/unit/test_list_json.py` | Create | Tests for `_build_list_json` + `cmd_list(--json)`. |
| `tests/unit/test_doctor_json.py` | Create | Tests for `DoctorCollector` + `cmd_doctor(--json)`. |
| `tests/unit/test_config_add_project.py` | Create | Tests for `cmd_config_add_project` (happy path + every rejection branch). |
| `docs/superpowers/specs/2026-05-26-gui-design.md` | Read | Authoritative JSON shape; do not let the plan diverge from it. |

The four CLI changes are independent at the helper level — each task adds a fresh `_*_json` builder. They share only the `argparse` table and the `COMMANDS` dispatch dict.

---

## Task 1: `machine ps --json`

**Files:**
- Modify: `bin/machine` (around `cmd_ps` at line 962 and `build_parser` at line 1993)
- Create: `tests/unit/test_ps_json.py`

The current `_make_ps_row` returns a `PsRow` of formatted strings (`"2h 14m"`, `"1.8 / 8 G"`, `"—"`). For JSON we add a parallel `_make_ps_row_json` that returns a dict of raw numbers / `None` — the same input data, a different presentation. The existing path is untouched.

- [ ] **Step 1.1: Write the failing tests**

Create `tests/unit/test_ps_json.py`:

```python
"""Tests for the JSON output of `machine ps --json`."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent.parent


def _load_machine():
    loader = SourceFileLoader("machine_cli", str(REPO / "bin" / "machine"))
    spec = importlib.util.spec_from_loader("machine_cli", loader)
    assert spec
    mod = importlib.util.module_from_spec(spec)
    sys.modules["machine_cli"] = mod
    loader.exec_module(mod)
    return mod


m = _load_machine()


class TestMakePsRowJson(unittest.TestCase):
    def test_running_vm_full_payload(self):
        project = {"repos": ["git@github.com:you/blog.git"], "profiles": ["cypress"]}
        lima_obj = {
            "status": "Running",
            "cpus": 4,
            # Lima's "uptime" / "uptime_seconds" varies by version; the helper
            # should call _vm_uptime() which we mock separately.
        }
        info = {
            "load1": 0.4,                          # 4 CPUs → 10% cpu
            "mem_used_bytes": 1_932_735_283,
            "mem_total_bytes": 8_589_934_592,
            "branch": "main",
            "idle_seconds": 180,
        }
        with mock.patch.object(m, "_vm_uptime", return_value="2h 14m"):
            row = m._make_ps_row_json("blog", project, lima_obj, info, [3000, 5173])

        self.assertEqual(row["name"], "blog")
        self.assertEqual(row["status"], "Running")
        self.assertAlmostEqual(row["cpu_percent"], 10.0, places=1)
        self.assertEqual(row["mem_used_bytes"], 1_932_735_283)
        self.assertEqual(row["mem_total_bytes"], 8_589_934_592)
        self.assertEqual(row["primary_repo"], "blog")
        self.assertEqual(row["branch"], "main")
        self.assertEqual(row["idle_seconds"], 180)
        self.assertEqual(row["ports"], [3000, 5173])
        self.assertEqual(row["profiles"], ["cypress"])
        self.assertEqual(row["repos"], ["git@github.com:you/blog.git"])

    def test_stopped_vm_has_null_runtime_fields(self):
        project = {"repos": ["git@github.com:you/blog.git"]}
        lima_obj = {"status": "Stopped"}
        row = m._make_ps_row_json("blog", project, lima_obj, {}, [])
        self.assertEqual(row["status"], "Stopped")
        self.assertIsNone(row["cpu_percent"])
        self.assertIsNone(row["mem_used_bytes"])
        self.assertIsNone(row["mem_total_bytes"])
        self.assertIsNone(row["idle_seconds"])
        self.assertIsNone(row["branch"])
        self.assertEqual(row["ports"], [])

    def test_missing_vm_status_is_missing(self):
        """A project in projects.toml without a corresponding Lima VM."""
        project = {"repos": ["git@github.com:you/api.git"]}
        row = m._make_ps_row_json("api", project, {}, {}, [])
        self.assertEqual(row["status"], "Missing")
        self.assertEqual(row["primary_repo"], "api")

    def test_orphan_lima_vm_has_no_project_config(self):
        """A Lima VM not in projects.toml (e.g. user destroyed the toml entry)."""
        row = m._make_ps_row_json("ghost", None, {"status": "Running"}, {}, [])
        self.assertEqual(row["name"], "ghost")
        self.assertEqual(row["status"], "Running")
        self.assertIsNone(row["primary_repo"])
        self.assertEqual(row["repos"], [])
        self.assertEqual(row["profiles"], [])

    def test_timed_out_info_returns_nulls_not_strings(self):
        """If the in-VM probe times out, JSON output must be null — not '?'."""
        project = {"repos": ["git@github.com:you/blog.git"]}
        lima_obj = {"status": "Running", "cpus": 4}
        info = {"_timed_out": True}
        with mock.patch.object(m, "_vm_uptime", return_value="14m"):
            row = m._make_ps_row_json("blog", project, lima_obj, info, [])
        self.assertEqual(row["status"], "Running")
        self.assertIsNone(row["cpu_percent"])
        self.assertIsNone(row["mem_used_bytes"])
        self.assertIsNone(row["idle_seconds"])
        self.assertIsNone(row["branch"])


class TestCmdPsJson(unittest.TestCase):
    """`cmd_ps(--json)` prints a single JSON array on stdout, no other lines."""

    def test_json_flag_prints_array(self):
        fake_cfg_path = Path("/tmp/test_projects.toml")
        fake_cfg_text = (
            'default_profile = "cypress"\n'
            '[blog]\nrepos = ["git@github.com:you/blog.git"]\n'
        )
        with mock.patch.object(m, "PROJECTS_FILE", fake_cfg_path), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=fake_cfg_text), \
             mock.patch.object(m, "_gather_lima_list_json", return_value={}), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
            rc = m.cmd_ps(mock.Mock(json=True))

        self.assertEqual(rc, 0)
        out = fake_stdout.getvalue()
        # Must be a single valid JSON array
        parsed = json.loads(out)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "blog")
        self.assertEqual(parsed[0]["status"], "Missing")

    def test_no_json_flag_prints_table(self):
        """Default path is unchanged — emits the table, not JSON."""
        fake_cfg_text = '[blog]\nrepos = ["git@github.com:you/blog.git"]\n'
        with mock.patch.object(m, "PROJECTS_FILE", Path("/tmp/x.toml")), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=fake_cfg_text), \
             mock.patch.object(m, "_gather_lima_list_json", return_value={}), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
            m.cmd_ps(mock.Mock(json=False))
        out = fake_stdout.getvalue()
        self.assertIn("NAME", out)        # table header
        self.assertIn("blog", out)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 1.2: Run the test to confirm it fails**

```
bash tests/unit.sh 2>&1 | grep -E "test_ps_json|FAIL|ERROR" | head -20
```

Expected: `AttributeError: module 'machine_cli' has no attribute '_make_ps_row_json'` (or similar — the function doesn't exist yet).

- [ ] **Step 1.3: Implement `_make_ps_row_json`**

In `bin/machine`, immediately **after** the existing `_make_ps_row` function (around line 907), add:

```python
def _make_ps_row_json(
    name: str,
    project: dict | None,
    lima_obj: dict,
    info: dict,
    active_ports: list[int],
) -> dict:
    """Build a single ps row as a JSON-friendly dict.

    Raw machine-readable numbers (seconds / bytes / percent floats) — None
    where a value is genuinely unknown. The GUI formats for display.
    Parallel of `_make_ps_row` (which produces the human table strings).
    """
    if not lima_obj:
        status = "Missing"
    else:
        status = lima_obj.get("status") or "Missing"

    is_running = status == "Running"
    timed_out = info.get("_timed_out", False)

    # Uptime — reuse the existing helper, but it returns a human string.
    # Translate "2h 14m" back to seconds via the underlying data when possible.
    uptime_seconds: int | None = None
    if is_running:
        # _vm_uptime returns a formatted string; for JSON we want raw seconds.
        # The Lima object usually has an "uptime"/"started" field; if not,
        # falling back to None is acceptable — the GUI tolerates it.
        raw_uptime = lima_obj.get("uptime") or lima_obj.get("uptimeSeconds")
        if isinstance(raw_uptime, (int, float)):
            uptime_seconds = int(raw_uptime)

    cpu_percent: float | None = None
    if is_running and not timed_out and info.get("load1") is not None:
        cpus = lima_obj.get("cpus") or 1
        cpu_percent = round((info["load1"] / cpus) * 100, 2)

    mem_used = mem_total = None
    if is_running and not timed_out:
        mem_used = info.get("mem_used_bytes")
        mem_total = info.get("mem_total_bytes")

    idle_seconds: int | None = None
    if is_running and not timed_out and info.get("idle_seconds") is not None:
        idle_seconds = int(info["idle_seconds"])

    primary = _primary_repo_basename(project) if project else None
    branch: str | None = None
    if is_running and not timed_out:
        b = info.get("branch")
        if isinstance(b, str):
            branch = b

    profiles: list[str] = []
    repos: list[str] = []
    if isinstance(project, dict):
        profiles = [p for p in (project.get("profiles") or []) if isinstance(p, str)]
        repos = [r for r in (project.get("repos") or []) if isinstance(r, str)]

    return {
        "name": name,
        "status": status,
        "uptime_seconds": uptime_seconds,
        "cpu_percent": cpu_percent,
        "mem_used_bytes": mem_used,
        "mem_total_bytes": mem_total,
        "primary_repo": primary,
        "branch": branch,
        "idle_seconds": idle_seconds,
        "ports": list(active_ports) if active_ports else [],
        "profiles": profiles,
        "repos": repos,
    }
```

Then add a parallel `_build_ps_rows_json` immediately below the existing `_build_ps_rows`. It's structurally identical — the only diff is the row builder it calls:

```python
def _build_ps_rows_json(cfg: dict, lima_vms: dict[str, dict]) -> list[dict]:
    """JSON-shaped twin of _build_ps_rows."""
    project_names = [k for k, v in cfg.items() if isinstance(v, dict) and k != "default_profile"]
    all_names = list(dict.fromkeys([*project_names, *lima_vms.keys()]))

    running = [n for n in all_names if lima_vms.get(n, {}).get("status") == "Running"]
    info_futures: dict[str, dict] = {}
    ports_futures: dict[str, list[int]] = {}

    if running:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(running))) as pool:
            info_tasks = {
                n: pool.submit(_gather_running_vm_info, n, _primary_repo_basename(cfg.get(n)))
                for n in running
            }
            port_tasks = {n: pool.submit(_gather_active_ports, n) for n in running}
            for n, fut in info_tasks.items():
                try:
                    info_futures[n] = fut.result(timeout=5.0)
                except concurrent.futures.TimeoutError:
                    info_futures[n] = {"_timed_out": True}
                except Exception:
                    info_futures[n] = {}
            for n, fut in port_tasks.items():
                try:
                    ports_futures[n] = fut.result(timeout=4.0)
                except Exception:
                    ports_futures[n] = []

    return [
        _make_ps_row_json(
            name,
            cfg.get(name),
            lima_vms.get(name, {}),
            info_futures.get(name, {}),
            ports_futures.get(name, []),
        )
        for name in all_names
    ]
```

- [ ] **Step 1.4: Wire `--json` into `cmd_ps`**

Replace the body of `cmd_ps` (currently lines 962-971) with:

```python
def cmd_ps(args: argparse.Namespace) -> int:
    if not PROJECTS_FILE.is_file():
        if getattr(args, "json", False):
            print("[]")
            return 0
        print(f"no {PROJECTS_FILE} — copy projects.toml.example and edit")
        return 0
    cfg = tomllib.loads(PROJECTS_FILE.read_text())
    lima_vms = _gather_lima_list_json()

    if getattr(args, "json", False):
        print(json.dumps(_build_ps_rows_json(cfg, lima_vms), indent=2))
        return 0

    rows = _build_ps_rows(cfg, lima_vms)
    _print_ps_table(rows)
    return 0
```

- [ ] **Step 1.5: Add the `--json` flag in `build_parser`**

Find the line in `build_parser` (around line 1993):

```python
    sub.add_parser("ps", help="Rich live-status table for all VMs (uptime, cpu/mem, repo, idle, ports)")
```

Replace it with:

```python
    ps = sub.add_parser("ps", help="Rich live-status table for all VMs (uptime, cpu/mem, repo, idle, ports)")
    ps.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON instead of the table (used by machine.app)")
```

- [ ] **Step 1.6: Run the tests to confirm they pass**

```
bash tests/unit.sh 2>&1 | tail -30
```

Expected: all tests in `test_ps_json.py` pass, no regressions in `test_ps.py` / `test_machine.py`.

- [ ] **Step 1.7: Manual smoke**

```
./bin/machine ps --json | python3 -m json.tool | head -40
```

Expected: a valid JSON array. Each entry has the keys listed in the spec.

- [ ] **Step 1.8: Commit**

```bash
git add bin/machine tests/unit/test_ps_json.py
git commit -m "Add --json output to machine ps

Emits a raw-typed (seconds, bytes, percents) JSON array of project
rows. Used by the upcoming Tauri GUI; the human table path is
untouched.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `machine list --json`

**Files:**
- Modify: `bin/machine` (around `cmd_list` at line 519 and `build_parser`)
- Create: `tests/unit/test_list_json.py`

`list --json` is **static config only** — no Lima probing, no parallel info gathering. Cheap to call; reflects what's in `projects.toml` regardless of whether the VMs exist.

- [ ] **Step 2.1: Write the failing tests**

Create `tests/unit/test_list_json.py`:

```python
"""Tests for the JSON output of `machine list --json`."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent.parent


def _load_machine():
    loader = SourceFileLoader("machine_cli", str(REPO / "bin" / "machine"))
    spec = importlib.util.spec_from_loader("machine_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["machine_cli"] = mod
    loader.exec_module(mod)
    return mod


m = _load_machine()


class TestBuildListJson(unittest.TestCase):
    def test_basic_project_with_default_profile(self):
        cfg = {
            "default_profile": "cypress",
            "blog": {"repos": ["git@github.com:you/blog.git"]},
        }
        out = m._build_list_json(cfg)
        self.assertEqual(out, [{
            "name": "blog",
            "repos": ["git@github.com:you/blog.git"],
            "primary_repo": "blog",
            "profiles": ["cypress"],
            "shell": None,
        }])

    def test_explicit_profiles_override_default(self):
        cfg = {
            "default_profile": "cypress",
            "wallet": {
                "repos": ["git@github.com:you/wallet.git", "git@github.com:you/gateway.git"],
                "profiles": ["cypress", "supabase-fly"],
                "shell": "fish",
            },
        }
        out = m._build_list_json(cfg)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["profiles"], ["cypress", "supabase-fly"])
        self.assertEqual(out[0]["shell"], "fish")
        self.assertEqual(out[0]["primary_repo"], "wallet")
        self.assertEqual(out[0]["repos"], [
            "git@github.com:you/wallet.git",
            "git@github.com:you/gateway.git",
        ])

    def test_no_default_profile_no_explicit_profile(self):
        cfg = {"api": {"repos": ["git@github.com:you/api.git"]}}
        out = m._build_list_json(cfg)
        self.assertEqual(out[0]["profiles"], [])

    def test_reserved_keys_excluded(self):
        """default_profile and default_shell are config, not projects."""
        cfg = {
            "default_profile": "cypress",
            "default_shell": "zsh",
            "blog": {"repos": ["git@github.com:you/blog.git"]},
        }
        out = m._build_list_json(cfg)
        names = [p["name"] for p in out]
        self.assertEqual(names, ["blog"])

    def test_string_value_skipped(self):
        """Per schema, string-valued top-level keys are placeholders, not projects."""
        cfg = {"blog": {"repos": ["git@github.com:you/blog.git"]}, "stale": "ignore me"}
        out = m._build_list_json(cfg)
        names = [p["name"] for p in out]
        self.assertEqual(names, ["blog"])


class TestCmdListJson(unittest.TestCase):
    def test_emits_valid_json(self):
        fake_text = (
            'default_profile = "cypress"\n'
            '[blog]\nrepos = ["git@github.com:you/blog.git"]\n'
        )
        with mock.patch.object(m, "PROJECTS_FILE", Path("/tmp/x.toml")), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=fake_text), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
            rc = m.cmd_list(mock.Mock(json=True))
        self.assertEqual(rc, 0)
        parsed = json.loads(fake_stdout.getvalue())
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "blog")
        self.assertEqual(parsed[0]["profiles"], ["cypress"])

    def test_no_json_flag_prints_table(self):
        """Default path unchanged."""
        fake_text = '[blog]\nrepos = ["git@github.com:you/blog.git"]\n'
        with mock.patch.object(m, "PROJECTS_FILE", Path("/tmp/x.toml")), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=fake_text), \
             mock.patch("subprocess.run", return_value=mock.Mock(stdout="", returncode=0)), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
            m.cmd_list(mock.Mock(json=False))
        out = fake_stdout.getvalue()
        self.assertIn("NAME", out)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2.2: Run the tests to confirm they fail**

```
bash tests/unit.sh 2>&1 | grep -E "test_list_json|FAIL|ERROR" | head -20
```

Expected: AttributeError on `_build_list_json`.

- [ ] **Step 2.3: Implement `_build_list_json`**

In `bin/machine`, immediately **before** the existing `cmd_list` definition (around line 519), add:

```python
def _build_list_json(cfg: dict) -> list[dict]:
    """Static `projects.toml` view: one dict per project, config only."""
    default_profile = cfg.get("default_profile")
    out: list[dict] = []
    for name, project in cfg.items():
        if name in ("default_profile", "default_shell"):
            continue
        if not isinstance(project, dict):
            continue
        repos = [r for r in (project.get("repos") or []) if isinstance(r, str)]
        explicit = project.get("profiles")
        if isinstance(explicit, list):
            profiles = [p for p in explicit if isinstance(p, str)]
        elif default_profile:
            profiles = [default_profile]
        else:
            profiles = []
        primary = _primary_repo_basename(project)
        out.append({
            "name": name,
            "repos": repos,
            "primary_repo": primary,
            "profiles": profiles,
            "shell": project.get("shell"),
        })
    return out
```

- [ ] **Step 2.4: Wire `--json` into `cmd_list`**

Replace the body of `cmd_list` (currently lines 519-546) with:

```python
def cmd_list(args: argparse.Namespace) -> int:
    if not PROJECTS_FILE.is_file():
        if getattr(args, "json", False):
            print("[]")
            return 0
        print(f"no {PROJECTS_FILE} — copy projects.toml.example and edit")
        return 0
    cfg = tomllib.loads(PROJECTS_FILE.read_text())

    if getattr(args, "json", False):
        print(json.dumps(_build_list_json(cfg), indent=2))
        return 0

    default = cfg.get("default_profile")
    # Live VM status, so a destroyed VM shows "—" instead of looking alive.
    proc = subprocess.run(
        ["limactl", "list", "--format={{.Name}} {{.Status}}"],
        capture_output=True, text=True,
    )
    status: dict[str, str] = {}
    for line in proc.stdout.strip().splitlines():
        parts = line.split()
        if parts:
            status[parts[0]] = " ".join(parts[1:])
    print(f"{'NAME':<20}  {'STATUS':<12}  {'PROFILES':<20}  REPO")
    for name, project in cfg.items():
        if not isinstance(project, dict):
            continue
        repos = project.get("repos", [])
        profiles = project.get("profiles") or ([default] if default else [])
        profile_str = ",".join(p for p in profiles if p) or "-"
        primary = repos[0] if repos else "-"
        extra = f" (+{len(repos)-1})" if len(repos) > 1 else ""
        st = status.get(name, "—")
        print(f"{name:<20}  {st:<12}  {profile_str:<20}  {primary}{extra}")
    return 0
```

- [ ] **Step 2.5: Add the `--json` flag in `build_parser`**

In `build_parser`, find:

```python
    sub.add_parser("list", help="List projects from projects.toml with live VM status")
```

Replace with:

```python
    ls = sub.add_parser("list", help="List projects from projects.toml with live VM status")
    ls.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON of projects.toml (no VM probing)")
```

- [ ] **Step 2.6: Run the tests**

```
bash tests/unit.sh 2>&1 | tail -30
```

Expected: all `test_list_json` tests pass.

- [ ] **Step 2.7: Manual smoke**

```
./bin/machine list --json | python3 -m json.tool
```

Expected: valid JSON, one entry per project.

- [ ] **Step 2.8: Commit**

```bash
git add bin/machine tests/unit/test_list_json.py
git commit -m "Add --json output to machine list

Static projects.toml view (no VM probing). Resolves default_profile
into the per-project profiles list so consumers don't have to.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `machine doctor --json`

**Files:**
- Modify: `bin/machine` — replace `cmd_doctor` (line 1806) and `doctor_ssh_config` (line 1699) to use a shared collector; add `--json` to `build_parser`.
- Create: `tests/unit/test_doctor_json.py`

The current `cmd_doctor` prints prose and tracks `state["fails"]` / `state["checks"]`. We introduce a single `DoctorCollector` that *either* prints prose as checks happen *or* silently records them, depending on `json_mode`. `cmd_doctor` and `doctor_ssh_config` are refactored to drive the collector instead of printing directly. Prose mode produces near-identical output to today (one new "hint:" line under failures); JSON mode emits a single `{checks, summary}` object.

- [ ] **Step 3.1: Write the failing tests**

Create `tests/unit/test_doctor_json.py`:

```python
"""Tests for the JSON output of `machine doctor --json`."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent.parent


def _load_machine():
    loader = SourceFileLoader("machine_cli", str(REPO / "bin" / "machine"))
    spec = importlib.util.spec_from_loader("machine_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["machine_cli"] = mod
    loader.exec_module(mod)
    return mod


m = _load_machine()


class TestDoctorCollector(unittest.TestCase):
    def test_record_ok(self):
        c = m.DoctorCollector()
        c.ok("limactl on PATH")
        self.assertEqual(c.results, [
            {"name": "limactl on PATH", "status": "ok", "detail": None, "hint": None},
        ])

    def test_record_ok_with_detail(self):
        c = m.DoctorCollector()
        c.ok("git user.name", detail="Jane Doe")
        self.assertEqual(c.results[0]["detail"], "Jane Doe")

    def test_record_fail(self):
        c = m.DoctorCollector()
        c.fail("SSH_AUTH_SOCK unset", hint="load a key with ssh-add")
        self.assertEqual(c.results, [
            {"name": "SSH_AUTH_SOCK unset", "status": "fail", "detail": None,
             "hint": "load a key with ssh-add"},
        ])

    def test_summary_counts(self):
        c = m.DoctorCollector()
        c.ok("a"); c.ok("b"); c.fail("c")
        self.assertEqual(c.summary(), {"checks": 3, "fails": 1})


class TestCmdDoctorJson(unittest.TestCase):
    """End-to-end: `cmd_doctor(--json)` returns a single valid JSON object."""

    def _patched_stack(self, stack: contextlib.ExitStack) -> None:
        """Push deterministic patches so the test isn't affected by host state."""
        stack.enter_context(mock.patch.object(
            m, "git_config",
            side_effect=lambda k: {"user.name": "Jane Doe",
                                   "user.email": "jane@example.com"}.get(k)))
        stack.enter_context(mock.patch.object(
            m, "read_signing_key", return_value="ssh-ed25519 AAAA..."))
        stack.enter_context(mock.patch.dict(
            os.environ, {"SSH_AUTH_SOCK": "/tmp/agent"}, clear=False))
        # doctor_ssh_config now takes a DoctorCollector — accept and ignore.
        stack.enter_context(mock.patch.object(
            m, "doctor_ssh_config", lambda c: None))
        stack.enter_context(mock.patch(
            "subprocess.run",
            return_value=mock.Mock(returncode=0,
                                   stdout="256 SHA256:abc user@host (ED25519)\n")))
        stack.enter_context(mock.patch.object(
            m, "PROJECTS_FILE", REPO / "projects.toml.example"))
        stack.enter_context(mock.patch(
            "shutil.which", return_value="/usr/local/bin/limactl"))

    def test_json_shape(self):
        with contextlib.ExitStack() as stack:
            self._patched_stack(stack)
            out = stack.enter_context(
                mock.patch("sys.stdout", new_callable=io.StringIO))
            rc = m.cmd_doctor(mock.Mock(json=True))
        payload = json.loads(out.getvalue())
        self.assertIn("checks", payload)
        self.assertIn("summary", payload)
        self.assertIsInstance(payload["checks"], list)
        for c in payload["checks"]:
            self.assertEqual(set(c.keys()), {"name", "status", "detail", "hint"})
            self.assertIn(c["status"], {"ok", "fail"})
        self.assertEqual(payload["summary"]["checks"], len(payload["checks"]))
        self.assertEqual(payload["summary"]["fails"],
                         sum(1 for c in payload["checks"] if c["status"] == "fail"))
        if payload["summary"]["fails"] == 0:
            self.assertEqual(rc, 0)
        else:
            self.assertEqual(rc, 1)

    def test_no_json_flag_prints_prose(self):
        with contextlib.ExitStack() as stack:
            self._patched_stack(stack)
            out = stack.enter_context(
                mock.patch("sys.stdout", new_callable=io.StringIO))
            m.cmd_doctor(mock.Mock(json=False))
        s = out.getvalue()
        self.assertIn("[doctor] host", s)   # section header
        self.assertIn("  ok  ", s)          # status line


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3.2: Run the tests to confirm they fail**

```
bash tests/unit.sh 2>&1 | grep -E "test_doctor_json|FAIL|ERROR" | head -20
```

Expected: AttributeError on `DoctorCollector`.

- [ ] **Step 3.3: Add the `DoctorCollector` class**

In `bin/machine`, **immediately before** `doctor_ssh_config` (around line 1699), add:

```python
class DoctorCollector:
    """Collects doctor check results. In prose mode, prints each one as it
    arrives (matching the historical format). In JSON mode, stays silent
    until `cmd_doctor` formats the final payload."""

    def __init__(self, json_mode: bool = False) -> None:
        self.json_mode = json_mode
        self.results: list[dict] = []
        self._section: str | None = None

    def section(self, label: str) -> None:
        self._section = label
        if not self.json_mode:
            print(f"[doctor] {label}")

    def ok(self, name: str, detail: str | None = None) -> None:
        self.results.append({
            "name": name, "status": "ok", "detail": detail, "hint": None,
        })
        if not self.json_mode:
            suffix = f" — {detail}" if detail else ""
            print(f"  ok  {name}{suffix}")

    def fail(self, name: str, *, detail: str | None = None, hint: str | None = None) -> None:
        self.results.append({
            "name": name, "status": "fail", "detail": detail, "hint": hint,
        })
        if not self.json_mode:
            suffix = f" — {detail}" if detail else ""
            print(f"  FAIL {name}{suffix}", file=sys.stderr)
            if hint:
                print(f"       hint: {hint}", file=sys.stderr)

    def warn(self, message: str) -> None:
        """Section-internal warning, not a check result. Prose-only."""
        if not self.json_mode:
            print(f"  WARN  {message}", file=sys.stderr)

    def summary(self) -> dict:
        return {
            "checks": len(self.results),
            "fails": sum(1 for r in self.results if r["status"] == "fail"),
        }
```

- [ ] **Step 3.4: Refactor `doctor_ssh_config` to use the collector**

`doctor_ssh_config(state)` currently prints its own `[doctor] ssh-config` header and `WARN` lines, and never touches `state["fails"]` (drift is WARN-level by design). Change its signature to `doctor_ssh_config(c: DoctorCollector) -> None` and replace every `print(...)` with the equivalent collector call.

The mapping rule:

| Old line | New call |
|---|---|
| `print("[doctor] ssh-config")` at top | `c.section("ssh-config")` |
| `print("  ok  <msg>")` | `c.ok("<msg>")` |
| `print(f"  WARN  <msg>", file=sys.stderr)` | `c.warn(f"<msg>")` |

Drift remains warn-level — these are NOT recorded as `fail` entries in the JSON output, only printed to stderr in prose mode. Walk through the function (lines 1699-end of `doctor_ssh_config`) and apply the mapping. No other logic changes.

- [ ] **Step 3.5: Refactor `cmd_doctor` to use the collector**

Replace the **entire body** of `cmd_doctor` (currently lines 1806-1894) with:

```python
def cmd_doctor(args: argparse.Namespace) -> int:
    json_mode = getattr(args, "json", False)
    c = DoctorCollector(json_mode=json_mode)

    class _HintError(Exception):
        def __init__(self, msg: str = "", hint: str | None = None) -> None:
            super().__init__(msg)
            self.hint = hint

    def check(label: str, fn) -> None:
        try:
            fn()
            c.ok(label)
        except _HintError as e:
            c.fail(label, detail=str(e) or None, hint=e.hint)
        except Exception as e:
            c.fail(label, detail=str(e) or None)

    def check_with_output(label: str, fn) -> None:
        try:
            out = fn()
            c.ok(label, detail=str(out) if out else None)
        except Exception as e:
            c.fail(label, detail=str(e) or None)

    def must(cond: bool, msg: str = "", hint: str | None = None) -> None:
        if not cond:
            raise _HintError(msg or "missing", hint=hint)

    def must_config(k: str) -> str:
        v = git_config(k)
        if not v:
            raise _HintError("(unset)", hint=f"git config --global {k} <value>")
        return v

    c.section("host")
    check("limactl on PATH", lambda: must(
        bool(shutil.which("limactl")), hint="brew install lima"))
    check("python3 with tomllib", lambda: tomllib)
    check_with_output("git user.name", lambda: must_config("user.name"))
    check_with_output("git user.email", lambda: must_config("user.email"))

    c.section("ssh")
    if os.environ.get("MACHINE_USE_1PASSWORD") == "1":
        sock = Path(os.environ.get("ONEPASS_SOCK") or ONEPASS_SOCK_DEFAULT)
        check("1Password agent socket", lambda: must(
            sock.is_socket(), str(sock),
            hint="enable: 1Password → Settings → Developer → 'Use the SSH agent'"))
    if os.environ.get("SSH_AUTH_SOCK"):
        check("SSH agent reachable",
              lambda: subprocess.run(["ssh-add", "-l"], check=True,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL))
        out = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True).stdout
        if not re.search(r"^(256|384|521|2048|3072|4096)", out, re.MULTILINE):
            c.fail("ssh-agent has a key loaded",
                   hint="ssh-add --apple-use-keychain ~/.ssh/id_ed25519")
        else:
            c.ok("ssh-agent has a key loaded")
    else:
        c.fail("SSH_AUTH_SOCK unset",
               hint="start your SSH agent or set MACHINE_USE_1PASSWORD=1")

    doctor_ssh_config(c)   # writes its own section + ok/warn lines

    c.section("signing key")
    try:
        sig = read_signing_key()
        c.ok("signing pubkey resolves", detail=f"{len(sig)} bytes")
    except SystemExit as e:
        c.fail("signing pubkey resolves", detail=str(e) or None,
               hint="set user.signingkey, GIT_SIGNING_KEY, or OP_SIGNING_KEY_REF")

    if os.environ.get("OP_SIGNING_KEY_REF") or (
        PROJECTS_FILE.is_file() and "op_env" in PROJECTS_FILE.read_text()
    ):
        c.section("1Password")
        check("op CLI installed", lambda: must(
            bool(shutil.which("op")), hint="brew install 1password-cli"))

    c.section("config")
    check("projects.toml present", lambda: must(
        PROJECTS_FILE.is_file(), str(PROJECTS_FILE),
        hint=f"machine init  # creates {PROJECTS_FILE}"))
    if PROJECTS_FILE.is_file():
        check("projects.toml parses",
              lambda: tomllib.loads(PROJECTS_FILE.read_text()))

    summary = c.summary()
    if json_mode:
        print(json.dumps({"checks": c.results, "summary": summary}, indent=2))
        return 0 if summary["fails"] == 0 else 1

    print()
    if summary["fails"] > 0:
        print(f"{summary['fails']}/{summary['checks']} checks failed", file=sys.stderr)
        return 1
    print(f"all {summary['checks']} checks passed")
    return 0
```

Key points:
- `_HintError` is the carrier for hint strings raised from inside lambdas. `check()` catches it and attaches `hint` to the result; other exceptions still produce a hint-less failure.
- `doctor_ssh_config(c)` is now the only call site of that helper — it prints its own `[doctor] ssh-config` section header and any drift warnings.
- The trailing `print()` blank line and summary line preserve the historical prose tail.

- [ ] **Step 3.6: Add the `--json` flag in `build_parser`**

In `build_parser`, find:

```python
    sub.add_parser("doctor", help="Preflight: lima, git config, SSH agent, signing key, op CLI")
```

Replace with:

```python
    doctor_p = sub.add_parser("doctor", help="Preflight: lima, git config, SSH agent, signing key, op CLI")
    doctor_p.add_argument("--json", action="store_true",
                          help="Emit machine-readable JSON {checks, summary} (used by machine.app)")
```

- [ ] **Step 3.7: Run the tests**

```
bash tests/unit.sh 2>&1 | tail -40
```

Expected: all `test_doctor_json` tests pass; no regressions elsewhere.

- [ ] **Step 3.8: Manual smoke (prose unchanged)**

Before this task, save the current output:

```
./bin/machine doctor > /tmp/doctor.before 2>&1 || true
```

After the refactor:

```
./bin/machine doctor > /tmp/doctor.after 2>&1 || true
diff -u /tmp/doctor.before /tmp/doctor.after || true
```

Expected diff: only new `hint:` lines under failures (those are net-new). Section headers and `ok` lines are unchanged. If a previously-passing check now fails (or vice versa), that's a real regression — fix it.

- [ ] **Step 3.9: Manual smoke (JSON path)**

```
./bin/machine doctor --json | python3 -m json.tool
```

Expected: a single JSON object with `checks` (array) and `summary` (`{checks, fails}`).

- [ ] **Step 3.10: Commit**

```bash
git add bin/machine tests/unit/test_doctor_json.py
git commit -m "Add --json output to machine doctor

Refactors cmd_doctor into a collector + two formatters (prose, JSON).
Prose output is preserved; --json emits {checks, summary} for the GUI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `machine config add-project`

**Files:**
- Modify: `bin/machine` (add `cmd_config_add_project` and a `config` subparser group)
- Create: `tests/unit/test_config_add_project.py`

This appends a project block to `projects.toml`. **Append-only**: refuses if the project name already exists, refuses if the named profile file doesn't exist, refuses on invalid name. The first-run modal in plan 2 calls this. We use string concatenation to write TOML (stdlib has no TOML writer) — safe here because we control every byte.

- [ ] **Step 4.1: Write the failing tests**

Create `tests/unit/test_config_add_project.py`:

```python
"""Tests for `machine config add-project`."""
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import tomllib
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent.parent


def _load_machine():
    loader = SourceFileLoader("machine_cli", str(REPO / "bin" / "machine"))
    spec = importlib.util.spec_from_loader("machine_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["machine_cli"] = mod
    loader.exec_module(mod)
    return mod


m = _load_machine()


def _tmp_projects(initial: str = "") -> Path:
    """Write a temp projects.toml and return its path."""
    fd, p = tempfile.mkstemp(suffix="-projects.toml")
    Path(p).write_text(initial)
    return Path(p)


class TestCmdConfigAddProject(unittest.TestCase):

    def _args(self, **kw):
        defaults = dict(name="myproj", repo="git@github.com:you/myproj.git", profile=[])
        defaults.update(kw)
        return mock.Mock(**defaults)

    def test_appends_to_empty_file(self):
        path = _tmp_projects("")
        with mock.patch.object(m, "PROJECTS_FILE", path):
            rc = m.cmd_config_add_project(self._args())
        self.assertEqual(rc, 0)
        parsed = tomllib.loads(path.read_text())
        self.assertIn("myproj", parsed)
        self.assertEqual(parsed["myproj"]["repos"], ["git@github.com:you/myproj.git"])

    def test_appends_to_existing_file_preserves_others(self):
        initial = (
            'default_profile = "cypress"\n'
            '[blog]\nrepos = ["git@github.com:you/blog.git"]\n'
        )
        path = _tmp_projects(initial)
        with mock.patch.object(m, "PROJECTS_FILE", path):
            rc = m.cmd_config_add_project(self._args(name="api", repo="git@github.com:you/api.git"))
        self.assertEqual(rc, 0)
        parsed = tomllib.loads(path.read_text())
        self.assertIn("blog", parsed)
        self.assertIn("api", parsed)
        self.assertEqual(parsed["default_profile"], "cypress")

    def test_with_profiles(self):
        path = _tmp_projects("")
        with mock.patch.object(m, "PROJECTS_FILE", path), \
             mock.patch.object(Path, "exists", return_value=True):
            rc = m.cmd_config_add_project(
                self._args(profile=["cypress", "supabase-fly"]))
        self.assertEqual(rc, 0)
        parsed = tomllib.loads(path.read_text())
        self.assertEqual(parsed["myproj"]["profiles"], ["cypress", "supabase-fly"])

    def test_refuses_existing_name(self):
        initial = '[blog]\nrepos = ["git@github.com:you/blog.git"]\n'
        path = _tmp_projects(initial)
        with mock.patch.object(m, "PROJECTS_FILE", path), \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(SystemExit) as ctx:
                m.cmd_config_add_project(self._args(name="blog"))
        self.assertNotEqual(ctx.exception.code, 0)
        self.assertIn("already exists", err.getvalue())

    def test_rejects_invalid_name(self):
        path = _tmp_projects("")
        with mock.patch.object(m, "PROJECTS_FILE", path):
            with self.assertRaises(SystemExit):
                m.cmd_config_add_project(self._args(name="Bad_Name"))

    def test_rejects_unknown_profile(self):
        path = _tmp_projects("")
        # Path.exists must return False for profiles/no-such.toml
        original_exists = Path.exists
        def fake_exists(self):
            if "no-such.toml" in str(self):
                return False
            return original_exists(self)
        with mock.patch.object(m, "PROJECTS_FILE", path), \
             mock.patch.object(Path, "exists", fake_exists), \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(SystemExit):
                m.cmd_config_add_project(self._args(profile=["no-such"]))
        self.assertIn("profile", err.getvalue().lower())

    def test_rejects_empty_repo(self):
        path = _tmp_projects("")
        with mock.patch.object(m, "PROJECTS_FILE", path):
            with self.assertRaises(SystemExit):
                m.cmd_config_add_project(self._args(repo=""))

    def test_output_is_idempotent_toml(self):
        """Multiple add-project calls produce a file that still parses cleanly."""
        path = _tmp_projects("")
        with mock.patch.object(m, "PROJECTS_FILE", path), \
             mock.patch.object(Path, "exists", return_value=True):
            m.cmd_config_add_project(self._args(name="a", repo="git@github.com:you/a.git"))
            m.cmd_config_add_project(self._args(name="b", repo="git@github.com:you/b.git",
                                                profile=["cypress"]))
            m.cmd_config_add_project(self._args(name="c", repo="git@github.com:you/c.git"))
        parsed = tomllib.loads(path.read_text())
        self.assertEqual(set(["a", "b", "c"]), set(k for k, v in parsed.items() if isinstance(v, dict)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4.2: Run the tests to confirm they fail**

```
bash tests/unit.sh 2>&1 | grep -E "test_config_add_project|FAIL|ERROR" | head -20
```

Expected: AttributeError on `cmd_config_add_project`.

- [ ] **Step 4.3: Implement `cmd_config_add_project`**

In `bin/machine`, add **immediately after** `cmd_validate` (around line 1969). The implementation has two helpers + the command:

```python
def _toml_quote(s: str) -> str:
    """Quote a string for TOML basic-string output. Only handles values we
    actually emit (URLs, identifiers, profile names) — no multi-line, no
    raw strings."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render_project_block(name: str, repo: str, profiles: list[str]) -> str:
    lines = [f"[{name}]", f"repos = [{_toml_quote(repo)}]"]
    if profiles:
        rendered = ", ".join(_toml_quote(p) for p in profiles)
        lines.append(f"profiles = [{rendered}]")
    return "\n".join(lines) + "\n"


def cmd_config_add_project(args: argparse.Namespace) -> int:
    name = args.name
    repo = (args.repo or "").strip()
    profiles = list(args.profile or [])

    validate_name(name)
    if not repo:
        die("--repo is required and must be non-empty")

    # Profile existence: every named profile must have a profiles/<p>.toml
    for p in profiles:
        if not NAME_RE.fullmatch(p):
            die(f"invalid profile name: {p!r}")
        path = REPO / "profiles" / f"{p}.toml"
        if not path.exists():
            die(f"profile {p!r} not found: {path} does not exist")

    # Load current TOML to check for name collision.
    if PROJECTS_FILE.is_file():
        existing_text = PROJECTS_FILE.read_text()
        try:
            existing = tomllib.loads(existing_text)
        except tomllib.TOMLDecodeError as e:
            die(f"{PROJECTS_FILE}: parse error before append: {e}")
    else:
        existing_text = ""
        existing = {}

    if name in existing and isinstance(existing[name], dict):
        die(f"project {name!r} already exists in {PROJECTS_FILE}")

    block = _render_project_block(name, repo, profiles)
    # Ensure exactly one blank line between blocks.
    if existing_text and not existing_text.endswith("\n"):
        existing_text += "\n"
    if existing_text and not existing_text.endswith("\n\n"):
        existing_text += "\n"

    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.write_text(existing_text + block)

    # Validate the result parses (defense-in-depth).
    try:
        tomllib.loads(PROJECTS_FILE.read_text())
    except tomllib.TOMLDecodeError as e:
        die(f"{PROJECTS_FILE}: produced invalid TOML — {e}")

    print(f"added [{name}] to {PROJECTS_FILE}")
    return 0
```

- [ ] **Step 4.4: Wire up the `config` subcommand group**

In `build_parser`, **immediately before** the `return p` line (around line 2044), add:

```python
    config_p = sub.add_parser("config", help="Manage projects.toml (machine-driven; the GUI calls this)")
    config_sub = config_p.add_subparsers(dest="config_action", metavar="<action>")
    add_p = config_sub.add_parser("add-project", help="Append a project to projects.toml (refuses overwrite)")
    add_p.add_argument("name", help="Project (VM) name; lowercase a-z, 0-9, hyphen")
    add_p.add_argument("--repo", required=True, help="Primary git remote (e.g., git@github.com:you/repo.git)")
    add_p.add_argument("--profile", action="append", default=[],
                       metavar="NAME", help="Profile to attach (repeatable)")
```

And register the dispatch — modify `COMMANDS` (around line 2048) so `config` routes through a small dispatcher. **Replace** the `COMMANDS = { ... }` block with:

```python
def cmd_config(args: argparse.Namespace) -> int:
    action = getattr(args, "config_action", None)
    if action == "add-project":
        return cmd_config_add_project(args)
    die("machine config requires an action (e.g., add-project)")


COMMANDS = {
    "list": cmd_list,
    "ps": cmd_ps,
    "doctor": cmd_doctor,
    "validate": cmd_validate,
    "init": cmd_init,
    "up": cmd_up,
    "down": cmd_down,
    "ssh": cmd_ssh,
    "claude": cmd_claude,
    "status": cmd_status,
    "destroy": cmd_destroy,
    "rebuild": cmd_rebuild,
    "run": cmd_run,
    "secrets": cmd_secrets,
    "update": cmd_update,
    "bake": cmd_bake,
    "config": cmd_config,
}
```

- [ ] **Step 4.5: Run the tests**

```
bash tests/unit.sh 2>&1 | tail -40
```

Expected: all `test_config_add_project` tests pass.

- [ ] **Step 4.6: Manual smoke**

```
mkdir -p /tmp/machine-smoke
echo 'default_profile = "cypress"' > /tmp/machine-smoke/projects.toml
PROJECTS_FILE=/tmp/machine-smoke/projects.toml ./bin/machine config add-project demo --repo "git@github.com:you/demo.git" --profile cypress
cat /tmp/machine-smoke/projects.toml
PROJECTS_FILE=/tmp/machine-smoke/projects.toml ./bin/machine validate
```

Expected: `demo` block appended, `machine validate` reports OK.

- [ ] **Step 4.7: Try the overwrite-refusal path**

```
PROJECTS_FILE=/tmp/machine-smoke/projects.toml ./bin/machine config add-project demo --repo "git@github.com:you/demo2.git" ; echo "exit=$?"
```

Expected: prints `machine: project 'demo' already exists ...`, exits non-zero.

- [ ] **Step 4.8: Run shellcheck/lint pass**

```
bash tests/lint.sh
```

Expected: clean.

- [ ] **Step 4.9: Commit**

```bash
git add bin/machine tests/unit/test_config_add_project.py
git commit -m "Add 'machine config add-project' subcommand

Append-only writer for projects.toml. Validates name, repo, and that
every named profile file exists; refuses to overwrite an existing
project entry. Used by the upcoming GUI's first-run modal — keeps all
projects.toml mutation in Python where the schema lives.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-review checklist (for the implementer)

After the four tasks are merged:

- [ ] `./bin/machine ps --json | python3 -m json.tool` succeeds.
- [ ] `./bin/machine list --json | python3 -m json.tool` succeeds.
- [ ] `./bin/machine doctor --json | python3 -m json.tool` succeeds; exit code matches `summary.fails > 0`.
- [ ] `./bin/machine config add-project foo --repo git@github.com:you/foo.git` adds the entry; running it again exits non-zero.
- [ ] `./bin/machine doctor` (no flag) prose output is unchanged (eyeball-equal to before).
- [ ] `./bin/machine ps` / `./bin/machine list` (no flag) tables are unchanged.
- [ ] `bash tests/unit.sh` is green.
- [ ] `bash tests/lint.sh` is green.
- [ ] `./bin/machine --help` shows the new `config` subcommand.
- [ ] Each commit message follows the existing repo style (imperative subject, terse body explaining the why, Co-Authored-By).

Once all green, this plan is done — proceed to plan 2 (`docs/superpowers/plans/2026-05-26-gui-plan-2-app.md`, to be written).
