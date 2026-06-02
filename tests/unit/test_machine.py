"""Unit tests for the host-side helpers in bin/machine. No VM required."""
import importlib.util
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_machine(extra_env: dict[str, str] | None = None):
    """Import bin/machine fresh with a controlled environment."""
    for key, value in (extra_env or {}).items():
        os.environ[key] = value
    # bin/machine has no .py suffix, so spec_from_file_location can't infer a
    # loader; build one explicitly via SourceFileLoader.
    loader = SourceFileLoader("machine_cli", str(ROOT / "bin" / "machine"))
    spec = importlib.util.spec_from_loader("machine_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class TestHelpers(unittest.TestCase):
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

    def test_repo_basename(self):
        self.assertEqual(self.m.repo_basename("git@github.com:me/blog.git"), "blog")
        self.assertEqual(self.m.repo_basename("https://github.com/me/x"), "x")

    def test_validate_name_rejects_bad(self):
        with self.assertRaises(SystemExit):
            self.m.validate_name("Bad_Name")
        self.m.validate_name("ok-name-2")  # no raise

    def test_default_profiles(self):
        self.assertEqual(self.m.default_profiles({}), [])
        self.assertEqual(
            self.m.default_profiles({"default_profile": "cypress"}), ["cypress"])
        self.assertEqual(self.m.default_profiles({"default_profile": ""}), [])

    def test_project_profiles_default_and_explicit(self):
        self.assertEqual(self.m.project_profiles("blog"), ["cypress"])
        self.assertEqual(self.m.project_profiles("wallet"), ["cypress", "supabase-fly"])
        self.assertEqual(self.m.project_profiles("bare"), [])

    def test_project_shell(self):
        self.assertEqual(self.m.project_shell("blog"), "zsh")
        self.assertEqual(self.m.project_shell("wallet"), "fish")

    def test_param_set_args_quotes_values(self):
        args = self.m.param_set_args(
            {"gitName": 'Ivan "K"', "shell": "zsh"})
        self.assertEqual(args[0], "--set")
        self.assertIn('.param.gitName = "Ivan \\"K\\""', args[1])
        self.assertIn('.param.shell = "zsh"', args[3])

    def test_render_template_without_golden(self):
        out = self.m.render_template("wallet", ["cypress", "supabase-fly"], golden=False)
        text = out.read_text()
        self.assertIn("base:", text)
        self.assertNotIn("file://", text)
        # Lima prepends each successively merged base, so profiles are listed
        # reversed and base.yaml last → base.sh executes first.
        entries = [l for l in text.splitlines() if l.startswith("- ")]
        self.assertTrue(entries[0].endswith("templates/supabase-fly.yaml"))
        self.assertTrue(entries[1].endswith("templates/cypress.yaml"))
        self.assertTrue(entries[2].endswith("templates/base.yaml"))

    def test_render_template_with_golden(self):
        img = Path(self.tmp.name) / "base-arm64.img"
        img.write_bytes(b"fake")
        out = self.m.render_template("wallet", [], golden=True, golden_image=img)
        text = out.read_text()
        self.assertIn(f"file://{img}", text)
        # images come before base so the cached disk wins
        self.assertLess(text.index("images:"), text.index("base:"))

    def test_render_template_rejects_unknown_profile(self):
        with self.assertRaises(SystemExit):
            self.m.render_template("wallet", ["nope"], golden=False)


class TestZeroConfig(unittest.TestCase):
    """Behavior with no projects.toml at all (zero-config mode)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = load_machine({
            "PROJECTS_FILE": str(Path(self.tmp.name) / "projects.toml"),
            "MACHINE_STATE_DIR": str(Path(self.tmp.name) / "state"),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_projects_missing_file_returns_empty(self):
        self.assertEqual(self.m.load_projects(), {})


if __name__ == "__main__":
    unittest.main()
