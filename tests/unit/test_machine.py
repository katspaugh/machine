"""Unit tests for pure helpers in bin/machine. No VM required."""
from __future__ import annotations

import datetime
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
            (fake / "lima.yaml").write_text("c")
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


class TestVerifyReposReachable(unittest.TestCase):
    def test_routes_message_through_renderer_raw(self):
        """When a renderer is provided, the access-check message must go through
        renderer.raw() rather than stdout."""
        stub = mock.MagicMock()
        fake_future = mock.MagicMock()
        fake_future.result.return_value = ""  # no error

        def fake_submit(fn, url):
            return fake_future

        fake_pool = mock.MagicMock()
        fake_pool.__enter__ = mock.Mock(return_value=fake_pool)
        fake_pool.__exit__ = mock.Mock(return_value=False)
        fake_pool.submit.side_effect = fake_submit

        with mock.patch("concurrent.futures.ThreadPoolExecutor", return_value=fake_pool), \
             mock.patch("concurrent.futures.as_completed", return_value=[fake_future]):
            with mock.patch("builtins.print") as mock_print:
                m.verify_repos_reachable(["git@github.com:org/repo.git"], renderer=stub)

        stub.raw.assert_called_once()
        call_arg = stub.raw.call_args[0][0]
        self.assertIn("checking access", call_arg)
        mock_print.assert_not_called()

    def test_falls_back_to_print_without_renderer(self):
        """When no renderer is provided, the message falls back to print()."""
        fake_future = mock.MagicMock()
        fake_future.result.return_value = ""

        fake_pool = mock.MagicMock()
        fake_pool.__enter__ = mock.Mock(return_value=fake_pool)
        fake_pool.__exit__ = mock.Mock(return_value=False)
        fake_pool.submit.return_value = fake_future

        with mock.patch("concurrent.futures.ThreadPoolExecutor", return_value=fake_pool), \
             mock.patch("concurrent.futures.as_completed", return_value=[fake_future]):
            with mock.patch("builtins.print") as mock_print:
                m.verify_repos_reachable(["git@github.com:org/repo.git"])

        mock_print.assert_called_once()
        self.assertIn("checking access", mock_print.call_args[0][0])

    def test_empty_urls_is_noop(self):
        """Empty URL list returns immediately without printing or checking."""
        stub = mock.MagicMock()
        with mock.patch("builtins.print") as mock_print:
            m.verify_repos_reachable([], renderer=stub)
        stub.raw.assert_not_called()
        mock_print.assert_not_called()


class TestCpuNormalization(unittest.TestCase):
    def test_cpu_normalized_by_cpu_count(self):
        """load1=2.0 with 4 CPUs → 50%."""
        info = {"load1": 2.0, "mem_used_bytes": None, "mem_total_bytes": None,
                "idle_seconds": None, "branch": None}
        row = m._make_ps_row("vm", None, {"status": "Running", "cpus": 4}, info, [])
        self.assertEqual(row.cpu, "50%")

    def test_cpu_overload_shows_gt_100(self):
        """load1=2.5 with 1 CPU → >100%."""
        info = {"load1": 2.5, "mem_used_bytes": None, "mem_total_bytes": None,
                "idle_seconds": None, "branch": None}
        row = m._make_ps_row("vm", None, {"status": "Running", "cpus": 1}, info, [])
        self.assertEqual(row.cpu, ">100%")

    def test_cpu_missing_cpus_defaults_to_1(self):
        """If lima_obj has no 'cpus', fall back to 1."""
        info = {"load1": 0.5, "mem_used_bytes": None, "mem_total_bytes": None,
                "idle_seconds": None, "branch": None}
        row = m._make_ps_row("vm", None, {"status": "Running"}, info, [])
        self.assertEqual(row.cpu, "50%")


class TestMemFormula(unittest.TestCase):
    def test_mem_formula_uses_memtotal_minus_available(self):
        """mem_used = total - available, not free's 'used' column."""
        # free -b output: total=4G, used=1G (free col), free=2.5G, shared=20M,
        #   buff/cache=500M, available=3.5G → real used = 4G - 3.5G = 500M
        free_block = (
            "              total        used        free      shared  buff/cache   available\n"
            "Mem:    4000000000  1000000000  2500000000    20000000   500000000  3500000000\n"
        )
        output = free_block + "---\n---\n"
        result = m._parse_vm_info("---\n" + free_block)
        self.assertEqual(result["mem_used_bytes"], 500000000)
        self.assertNotEqual(result["mem_used_bytes"], 1000000000)


class TestParseWhoIdle(unittest.TestCase):
    def _now(self):
        return datetime.datetime(2026, 5, 23, 16, 0, 0)

    def test_takes_most_recent_login(self):
        """Returns delta from the most recent (later) login time."""
        who_out = (
            "ivan     pts/0        2026-05-23 14:30 (10.0.2.2)\n"
            "ivan     pts/1        2026-05-23 15:12 (10.0.2.2)\n"
        )
        # now=16:00, latest=15:12 → 48 minutes = 2880 seconds
        result = m._parse_who_idle(who_out, now=self._now())
        self.assertAlmostEqual(result, 2880.0, places=0)

    def test_empty_input_returns_none(self):
        self.assertIsNone(m._parse_who_idle(""))
        self.assertIsNone(m._parse_who_idle("   \n  "))

    def test_malformed_lines_skipped(self):
        """Lines without enough columns are ignored; valid line still parsed."""
        who_out = (
            "badline\n"
            "ivan     pts/0        2026-05-23 15:30 (10.0.2.2)\n"
        )
        # now=16:00, latest=15:30 → 30 minutes = 1800 seconds
        result = m._parse_who_idle(who_out, now=self._now())
        self.assertAlmostEqual(result, 1800.0, places=0)

    def test_no_parseable_lines_returns_none(self):
        who_out = "no date here at all\n"
        self.assertIsNone(m._parse_who_idle(who_out, now=self._now()))


class TestPsRowIdle(unittest.TestCase):
    def test_ps_row_shows_idle_for_running_vm(self):
        """IDLE column shows formatted duration when who has a login 30 min ago."""
        # supply idle_seconds directly (30 minutes = 1800 s).
        info = {"load1": None, "mem_used_bytes": None, "mem_total_bytes": None,
                "idle_seconds": 1800.0, "branch": None}
        row = m._make_ps_row("vm", None, {"status": "Running"}, info, [])
        self.assertEqual(row.idle, "30m")

    def test_ps_row_idle_em_dash_when_who_empty(self):
        """IDLE column shows — when idle_seconds is None."""
        info = {"load1": None, "mem_used_bytes": None, "mem_total_bytes": None,
                "idle_seconds": None, "branch": None}
        row = m._make_ps_row("vm", None, {"status": "Running"}, info, [])
        self.assertEqual(row.idle, "—")


class TestPsRowTimeout(unittest.TestCase):
    def test_row_shows_question_marks_on_timeout(self):
        """When _timed_out flag is set, cpu/mem/idle show '?'."""
        info = {"_timed_out": True}
        row = m._make_ps_row("vm", None, {"status": "Running"}, info, [])
        self.assertEqual(row.cpu, "?")
        self.assertEqual(row.mem, "?")
        self.assertEqual(row.idle, "?")


if __name__ == "__main__":
    unittest.main()
