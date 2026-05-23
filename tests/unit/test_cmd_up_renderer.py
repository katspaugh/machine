"""Tests for the Renderer helpers added to bin/machine for cmd_up."""
from __future__ import annotations

import argparse
import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .test_machine import m  # reuses the bin/machine module loader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_log(suffix=".log") -> str:
    """Return a writable temp file path in the sandbox-permitted TMPDIR."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDefaultProvisionLogPath(unittest.TestCase):
    def test_path_shape(self):
        path = m.default_provision_log_path("blog")
        # Should be under <STATE_DIR>/logs/
        self.assertEqual(path.parent, m.STATE_DIR / "logs")
        # Filename should match blog-<ISO8601>.log
        pattern = re.compile(r"^blog-\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\.log$")
        self.assertRegex(path.name, pattern)

    def test_different_vms_have_different_names(self):
        p1 = m.default_provision_log_path("alpha")
        p2 = m.default_provision_log_path("beta")
        self.assertNotEqual(p1.name, p2.name)
        self.assertTrue(p1.name.startswith("alpha-"))
        self.assertTrue(p2.name.startswith("beta-"))


class TestMakeRendererEnvVars(unittest.TestCase):
    """make_renderer must honour env vars AND args.plain/args.verbose."""

    def _build_ns(self, plain=False, verbose=False):
        return argparse.Namespace(plain=plain, verbose=verbose)

    def setUp(self):
        # A fresh temp log file for each test — avoids ~/.machine permission issues.
        fd, self._log = tempfile.mkstemp(suffix=".log")
        os.close(fd)
        self._patch = mock.patch.dict(os.environ, {"MACHINE_PROVISION_LOG": self._log})
        self._patch.start()
        # Remove any inherited env vars that might interfere
        os.environ.pop("MACHINE_PLAIN", None)
        os.environ.pop("MACHINE_VERBOSE", None)

    def tearDown(self):
        self._patch.stop()
        try:
            os.unlink(self._log)
        except FileNotFoundError:
            pass

    def test_make_renderer_respects_plain_env(self):
        ns = self._build_ns(plain=False, verbose=False)
        with mock.patch.dict(os.environ, {"MACHINE_PLAIN": "1"}):
            r = m.make_renderer(ns, "blog")
        try:
            self.assertFalse(r._tty)
        finally:
            r.close()

    def test_make_renderer_plain_arg_sets_no_tty(self):
        ns = self._build_ns(plain=True, verbose=False)
        r = m.make_renderer(ns, "blog")
        try:
            self.assertFalse(r._tty)
        finally:
            r.close()

    def test_make_renderer_respects_verbose_env(self):
        ns = self._build_ns(plain=False, verbose=False)
        with mock.patch.dict(os.environ, {"MACHINE_VERBOSE": "1"}):
            r = m.make_renderer(ns, "blog")
        try:
            self.assertTrue(r._verbose)
        finally:
            r.close()

    def test_make_renderer_verbose_arg_sets_verbose(self):
        ns = self._build_ns(plain=False, verbose=True)
        r = m.make_renderer(ns, "blog")
        try:
            self.assertTrue(r._verbose)
        finally:
            r.close()

    def test_make_renderer_respects_machine_provision_log(self):
        ns = self._build_ns()
        r = m.make_renderer(ns, "blog")
        try:
            self.assertEqual(r._log_path, Path(self._log))
        finally:
            r.close()

    def test_make_renderer_uses_default_log_path_when_env_unset(self):
        ns = self._build_ns()
        # Build env without MACHINE_PROVISION_LOG
        env_without = {k: v for k, v in os.environ.items()
                       if k != "MACHINE_PROVISION_LOG"}
        with mock.patch.dict(os.environ, env_without, clear=True), \
             mock.patch.object(m, "default_provision_log_path",
                               return_value=Path(self._log)) as dp:
            r = m.make_renderer(ns, "testvm")
        try:
            dp.assert_called_once_with("testvm")
            self.assertEqual(r._log_path, Path(self._log))
        finally:
            r.close()

    def test_make_renderer_getattr_defaults_on_plain_namespace(self):
        """Namespace without plain/verbose attrs (like cmd_rebuild's synthetic one) works."""
        ns = argparse.Namespace(project="blog", dry_run=False)  # no plain or verbose
        r = m.make_renderer(ns, "blog")
        try:
            self.assertFalse(r._verbose)
        finally:
            r.close()


class TestRunQuiet(unittest.TestCase):
    def test_streams_stdout_and_stderr_to_renderer(self):
        """run_quiet merges stderr into stdout and calls renderer.raw() for each line."""
        raw_lines: list[str] = []

        class FakeRenderer:
            def raw(self, line: str) -> None:
                raw_lines.append(line)

        rc = m.run_quiet(
            ["sh", "-c", "echo hello; echo world >&2"],
            renderer=FakeRenderer(),
        )
        self.assertEqual(rc, 0)
        self.assertIn("hello", raw_lines)
        self.assertIn("world", raw_lines)

    def test_returns_nonzero_exit_code(self):
        class FakeRenderer:
            def raw(self, line: str) -> None:
                pass

        rc = m.run_quiet(["sh", "-c", "exit 42"], renderer=FakeRenderer())
        self.assertEqual(rc, 42)

    def test_lines_are_stripped_of_trailing_newline(self):
        captured: list[str] = []

        class FakeRenderer:
            def raw(self, line: str) -> None:
                captured.append(line)

        m.run_quiet(["sh", "-c", "printf 'no-newline'"], renderer=FakeRenderer())
        for line in captured:
            self.assertFalse(line.endswith("\n"),
                             f"line should not end with newline, got {line!r}")


class TestRunQuietWithRealRenderer(unittest.TestCase):
    """Integration test: run_quiet feeds output into a real Renderer (plain mode)."""

    def test_lines_appear_in_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "test.log"
            stream = io.StringIO()
            r = m.log_view.Renderer(stream, tty=False, verbose=True, log_path=log_path)
            with r:
                s = r.step_start("test step")
                rc = m.run_quiet(
                    ["sh", "-c", "echo hello; echo world >&2"],
                    renderer=r,
                )
                r.step_end(s, "ok")
            self.assertEqual(rc, 0)
            log_text = log_path.read_text()
            self.assertIn("hello", log_text)
            self.assertIn("world", log_text)
