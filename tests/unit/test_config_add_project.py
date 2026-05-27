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


def _tmp_projects(initial: str = "") -> Path:
    fd, p = tempfile.mkstemp(suffix="-projects.toml")
    Path(p).write_text(initial)
    return Path(p)


class TestCmdConfigAddProject(unittest.TestCase):

    def _args(self, **kw):
        defaults = dict(name="myproj", repo="git@github.com:you/myproj.git", profile=[])
        defaults.update(kw)
        # `name` is reserved by Mock's constructor (it sets the mock's display
        # name), so it must be assigned after construction to land as an attr.
        args = mock.Mock(repo=defaults["repo"], profile=defaults["profile"])
        args.name = defaults["name"]
        return args

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
        with mock.patch.object(m, "PROJECTS_FILE", path), \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(SystemExit):
                m.cmd_config_add_project(self._args(name="Bad_Name"))
        self.assertIn("invalid", err.getvalue().lower())

    def test_rejects_unknown_profile(self):
        path = _tmp_projects("")
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
        with mock.patch.object(m, "PROJECTS_FILE", path), \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(SystemExit):
                m.cmd_config_add_project(self._args(repo=""))
        self.assertIn("--repo", err.getvalue())

    def test_output_is_idempotent_toml(self):
        path = _tmp_projects("")
        with mock.patch.object(m, "PROJECTS_FILE", path), \
             mock.patch.object(Path, "exists", return_value=True):
            m.cmd_config_add_project(self._args(name="a", repo="git@github.com:you/a.git"))
            m.cmd_config_add_project(self._args(name="b", repo="git@github.com:you/b.git",
                                                profile=["cypress"]))
            m.cmd_config_add_project(self._args(name="c", repo="git@github.com:you/c.git"))
        parsed = tomllib.loads(path.read_text())
        self.assertEqual(set(["a", "b", "c"]),
                         set(k for k, v in parsed.items() if isinstance(v, dict)))

    def test_appends_to_file_without_trailing_newline(self):
        path = _tmp_projects('[a]\nrepos = ["git@github.com:you/a.git"]')  # no trailing \n
        with mock.patch.object(m, "PROJECTS_FILE", path):
            rc = m.cmd_config_add_project(self._args(name="b", repo="git@github.com:you/b.git"))
        self.assertEqual(rc, 0)
        parsed = tomllib.loads(path.read_text())
        self.assertIn("a", parsed)
        self.assertIn("b", parsed)

    def test_malicious_repo_does_not_inject_table(self):
        """A repo value with quotes/backslashes round-trips as a single string —
        no extra TOML table is created."""
        path = _tmp_projects("")
        evil = 'x"] [evil] repos = ["y'   # printable chars only (no real newline)
        with mock.patch.object(m, "PROJECTS_FILE", path):
            rc = m.cmd_config_add_project(self._args(name="safe", repo=evil))
        self.assertEqual(rc, 0)
        parsed = tomllib.loads(path.read_text())
        self.assertNotIn("evil", parsed)
        self.assertEqual(parsed["safe"]["repos"], [evil])

    def test_control_char_in_repo_is_rejected_and_file_untouched(self):
        """A real newline in --repo is rejected up front; existing file unchanged."""
        initial = '[keep]\nrepos = ["git@github.com:you/keep.git"]\n'
        path = _tmp_projects(initial)
        with mock.patch.object(m, "PROJECTS_FILE", path), \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(SystemExit):
                m.cmd_config_add_project(self._args(name="bad", repo='x\n[evil]\nrepos=["y'))
        self.assertIn("control character", err.getvalue().lower())
        # The pre-existing file must be byte-for-byte unchanged.
        self.assertEqual(path.read_text(), initial)
        parsed = tomllib.loads(path.read_text())
        self.assertNotIn("evil", parsed)
        self.assertNotIn("bad", parsed)


if __name__ == "__main__":
    unittest.main()
