"""Tests for the JSON output of `machine ps --json`."""
from __future__ import annotations

import argparse
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
    # Reuse an already-loaded module if a sibling test has imported it; loading
    # twice replaces sys.modules["machine_cli"] which breaks
    # `mock.patch("machine_cli._probe_port", ...)` in other test files because
    # the previously-bound function references the old module's globals.
    if "machine_cli" in sys.modules:
        return sys.modules["machine_cli"]
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
        lima_obj = {"status": "Running", "cpus": 4}
        info = {
            "load1": 0.4,
            "mem_used_bytes": 1_932_735_283,
            "mem_total_bytes": 8_589_934_592,
            "branch": "main",
            "idle_seconds": 180,
        }
        with mock.patch.object(m, "_vm_uptime_seconds", return_value=8040.0):
            row = m._make_ps_row_json("blog", project, lima_obj, info, [3000, 5173])
        self.assertEqual(row["name"], "blog")
        self.assertEqual(row["status"], "Running")
        self.assertEqual(row["uptime_seconds"], 8040)
        self.assertIsInstance(row["uptime_seconds"], int)
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
        project = {"repos": ["git@github.com:you/api.git"]}
        row = m._make_ps_row_json("api", project, {}, {}, [])
        self.assertEqual(row["status"], "Missing")
        self.assertEqual(row["primary_repo"], "api")

    def test_orphan_lima_vm_has_no_project_config(self):
        row = m._make_ps_row_json("ghost", None, {"status": "Running"}, {}, [])
        self.assertEqual(row["name"], "ghost")
        self.assertEqual(row["status"], "Running")
        self.assertIsNone(row["primary_repo"])
        self.assertEqual(row["repos"], [])
        self.assertEqual(row["profiles"], [])

    def test_timed_out_info_returns_nulls_not_strings(self):
        project = {"repos": ["git@github.com:you/blog.git"]}
        lima_obj = {"status": "Running", "cpus": 4}
        info = {"_timed_out": True}
        with mock.patch.object(m, "_vm_uptime_seconds", return_value=840.0):
            row = m._make_ps_row_json("blog", project, lima_obj, info, [])
        self.assertEqual(row["status"], "Running")
        self.assertIsNone(row["cpu_percent"])
        self.assertIsNone(row["mem_used_bytes"])
        self.assertIsNone(row["idle_seconds"])
        self.assertIsNone(row["branch"])

    def test_profiles_resolves_default_profile(self):
        project = {"repos": ["git@github.com:you/blog.git"]}  # no explicit profiles
        row = m._make_ps_row_json("blog", project, {"status": "Stopped"}, {}, [],
                                  default_profile="cypress")
        self.assertEqual(row["profiles"], ["cypress"])

    def test_profiles_empty_when_no_default(self):
        project = {"repos": ["git@github.com:you/blog.git"]}
        row = m._make_ps_row_json("blog", project, {"status": "Stopped"}, {}, [],
                                  default_profile=None)
        self.assertEqual(row["profiles"], [])

    def test_explicit_profiles_override_default(self):
        project = {"repos": ["x"], "profiles": ["go"]}
        row = m._make_ps_row_json("p", project, {"status": "Stopped"}, {}, [],
                                  default_profile="cypress")
        self.assertEqual(row["profiles"], ["go"])


class TestCmdPsJson(unittest.TestCase):
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
            rc = m.cmd_ps(argparse.Namespace(json=True))
        self.assertEqual(rc, 0)
        out = fake_stdout.getvalue()
        parsed = json.loads(out)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "blog")
        self.assertEqual(parsed[0]["status"], "Missing")

    def test_no_json_flag_prints_table(self):
        fake_cfg_text = '[blog]\nrepos = ["git@github.com:you/blog.git"]\n'
        with mock.patch.object(m, "PROJECTS_FILE", Path("/tmp/x.toml")), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=fake_cfg_text), \
             mock.patch.object(m, "_gather_lima_list_json", return_value={}), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
            m.cmd_ps(argparse.Namespace(json=False))
        out = fake_stdout.getvalue()
        self.assertIn("NAME", out)
        self.assertIn("blog", out)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)

    def test_no_projects_toml_emits_empty_array(self):
        with mock.patch.object(Path, "is_file", return_value=False), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = m.cmd_ps(argparse.Namespace(json=True))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue()), [])

    def test_ps_and_list_json_agree_on_profiles(self):
        import argparse, json as _json
        fake_text = ('default_profile = "cypress"\n'
                     '[blog]\nrepos = ["git@github.com:you/blog.git"]\n')
        def run(cmd):
            with mock.patch.object(m, "PROJECTS_FILE", Path("/tmp/x.toml")), \
                 mock.patch.object(Path, "is_file", return_value=True), \
                 mock.patch.object(Path, "read_text", return_value=fake_text), \
                 mock.patch.object(m, "_gather_lima_list_json", return_value={}), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                cmd(argparse.Namespace(json=True))
            return _json.loads(out.getvalue())
        ps_rows = run(m.cmd_ps)
        list_rows = run(m.cmd_list)
        ps_blog = next(r for r in ps_rows if r["name"] == "blog")
        list_blog = next(r for r in list_rows if r["name"] == "blog")
        self.assertEqual(ps_blog["profiles"], list_blog["profiles"])
        self.assertEqual(ps_blog["profiles"], ["cypress"])


if __name__ == "__main__":
    unittest.main()
