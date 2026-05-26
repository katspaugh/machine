"""Tests for the JSON output of `machine list --json`."""
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
    # Reuse cached module if present to avoid invalidating other test files'
    # patches under alphabetical discovery. See test_ps_json.py for the
    # underlying mechanism.
    cached = sys.modules.get("machine_cli")
    if cached is not None:
        return cached
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
        cfg = {
            "default_profile": "cypress",
            "default_shell": "zsh",
            "blog": {"repos": ["git@github.com:you/blog.git"]},
        }
        out = m._build_list_json(cfg)
        names = [p["name"] for p in out]
        self.assertEqual(names, ["blog"])

    def test_string_value_skipped(self):
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
            rc = m.cmd_list(argparse.Namespace(json=True))
        self.assertEqual(rc, 0)
        parsed = json.loads(fake_stdout.getvalue())
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "blog")
        self.assertEqual(parsed[0]["profiles"], ["cypress"])

    def test_no_json_flag_prints_table(self):
        fake_text = '[blog]\nrepos = ["git@github.com:you/blog.git"]\n'
        with mock.patch.object(m, "PROJECTS_FILE", Path("/tmp/x.toml")), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "read_text", return_value=fake_text), \
             mock.patch("subprocess.run", return_value=mock.Mock(stdout="", returncode=0)), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
            m.cmd_list(argparse.Namespace(json=False))
        out = fake_stdout.getvalue()
        self.assertIn("NAME", out)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)

    def test_no_projects_toml_emits_empty_array(self):
        with mock.patch.object(m, "PROJECTS_FILE", Path("/nonexistent/x.toml")), \
             mock.patch.object(Path, "is_file", return_value=False), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = m.cmd_list(argparse.Namespace(json=True))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue()), [])


if __name__ == "__main__":
    unittest.main()
