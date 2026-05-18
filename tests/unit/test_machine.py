"""Unit tests for pure helpers in bin/machine. No VM required."""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent.parent


def _load_machine() -> object:
    """Import bin/machine (extensionless Python script) as a module without
    executing main()."""
    loader = SourceFileLoader("machine_cli", str(REPO / "bin" / "machine"))
    spec = importlib.util.spec_from_loader("machine_cli", loader)
    assert spec
    mod = importlib.util.module_from_spec(spec)
    sys.modules["machine_cli"] = mod
    loader.exec_module(mod)
    return mod


m = _load_machine()


class TestRepoBasename(unittest.TestCase):
    def test_ssh_url_with_git_suffix(self):
        self.assertEqual(m.repo_basename("git@github.com:org/repo.git"), "repo")

    def test_https_url_with_git_suffix(self):
        self.assertEqual(m.repo_basename("https://github.com/org/repo.git"), "repo")

    def test_no_git_suffix(self):
        self.assertEqual(m.repo_basename("git@github.com:org/repo"), "repo")

    def test_dashes_in_name(self):
        self.assertEqual(m.repo_basename("git@github.com:org/my-cool-repo.git"), "my-cool-repo")


class TestValidateName(unittest.TestCase):
    def test_valid_names(self):
        for n in ("blog", "wallet", "my-app", "a1", "0abc"):
            m.validate_name(n)  # must not raise

    def test_invalid_names(self):
        for n in ("Foo", "-leading", "weird_name", "with space", "with.dot", ""):
            with self.assertRaises(SystemExit, msg=f"expected reject: {n}"):
                m.validate_name(n)


class TestGoldenArchTag(unittest.TestCase):
    def test_arm64_variants(self):
        with mock.patch.object(os, "uname", return_value=mock.Mock(machine="arm64")):
            self.assertEqual(m.golden_arch_tag(), "arm64")
        with mock.patch.object(os, "uname", return_value=mock.Mock(machine="aarch64")):
            self.assertEqual(m.golden_arch_tag(), "arm64")

    def test_x86_64(self):
        with mock.patch.object(os, "uname", return_value=mock.Mock(machine="x86_64")):
            self.assertEqual(m.golden_arch_tag(), "amd64")


class TestGoldenLimaArch(unittest.TestCase):
    def test_arm64_variants(self):
        with mock.patch.object(os, "uname", return_value=mock.Mock(machine="arm64")):
            self.assertEqual(m.golden_lima_arch(), "aarch64")
        with mock.patch.object(os, "uname", return_value=mock.Mock(machine="aarch64")):
            self.assertEqual(m.golden_lima_arch(), "aarch64")

    def test_x86_64(self):
        with mock.patch.object(os, "uname", return_value=mock.Mock(machine="x86_64")):
            self.assertEqual(m.golden_lima_arch(), "x86_64")


class TestGoldenHash(unittest.TestCase):
    def test_hash_changes_when_inputs_change(self):
        h1 = m.golden_hash()
        # Touch one of the inputs (deterministically). Use a fake REPO with
        # two writable files.
        import tempfile, shutil
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            (fake / "provision").mkdir()
            (fake / "provision.toml").write_text("a")
            (fake / "provision" / "run.py").write_text("b")
            with mock.patch.object(m, "REPO", fake):
                first = m.golden_hash()
                (fake / "provision.toml").write_text("a2")
                second = m.golden_hash()
        self.assertNotEqual(first, second)
        self.assertEqual(len(h1), 16)


class TestProjectQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.TemporaryDirectory()
        cls.projects = Path(cls.tmp.name) / "projects.toml"
        cls.projects.write_text(
            'default_profile = "cypress"\n'
            'default_shell = "fish"\n'
            '\n'
            '[blog]\n'
            'repos = ["git@github.com:you/blog.git"]\n'
            '\n'
            '[wallet]\n'
            'profiles = ["cypress", "supabase-fly"]\n'
            'shell = "bash"\n'
            'repos = ["git@github.com:you/a.git", "git@github.com:you/b.git"]\n'
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        # Each test gets a fresh PROJECTS_FILE patch.
        self._patch = mock.patch.object(m, "PROJECTS_FILE", self.projects)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_project_urls_single(self):
        self.assertEqual(m.project_urls("blog"), ["git@github.com:you/blog.git"])

    def test_project_urls_multi_preserves_order(self):
        self.assertEqual(
            m.project_urls("wallet"),
            ["git@github.com:you/a.git", "git@github.com:you/b.git"],
        )

    def test_project_urls_unknown_exits(self):
        with self.assertRaises(SystemExit):
            m.project_urls("nope")

    def test_project_profiles_explicit(self):
        self.assertEqual(m.project_profiles("wallet"), ["cypress", "supabase-fly"])

    def test_project_profiles_falls_back_to_default(self):
        self.assertEqual(m.project_profiles("blog"), ["cypress"])

    def test_project_shell_explicit(self):
        self.assertEqual(m.project_shell("wallet"), "bash")

    def test_project_shell_falls_back_to_default(self):
        self.assertEqual(m.project_shell("blog"), "fish")

    def test_project_shell_invalid_exits(self):
        bad = Path(self.tmp.name) / "bad.toml"
        bad.write_text('[x]\nrepos=["a"]\nshell="ksh"\n')
        with mock.patch.object(m, "PROJECTS_FILE", bad):
            with self.assertRaises(SystemExit):
                m.project_shell("x")


class TestLoadDotenv(unittest.TestCase):
    def test_loads_basic_kv(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            (fake / ".env").write_text(
                '# comment\n'
                'FOO=bar\n'
                'QUOTED="baz qux"\n'
                'SINGLE=\'one two\'\n'
                '\n'
            )
            with mock.patch.object(m, "REPO", fake), \
                 mock.patch.dict(os.environ, {}, clear=False):
                # Ensure starting state.
                for k in ("FOO", "QUOTED", "SINGLE"):
                    os.environ.pop(k, None)
                m.load_dotenv()
                self.assertEqual(os.environ.get("FOO"), "bar")
                self.assertEqual(os.environ.get("QUOTED"), "baz qux")
                self.assertEqual(os.environ.get("SINGLE"), "one two")


if __name__ == "__main__":
    unittest.main()
