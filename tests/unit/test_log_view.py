"""Unit tests for provision/log_view.py — Renderer class."""
from __future__ import annotations

import datetime
import io
import sys
import unittest
from pathlib import Path

# Make sure provision/ is importable from the repo root
REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from provision.log_view import Renderer, StepHandle  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixed_now(values: list[float]):
    """Return a callable that yields successive values from the list."""
    it = iter(values)
    return lambda: next(it)


def _fixed_wall(dt: datetime.datetime | None = None):
    """Return a wall_now callable that always returns the same datetime."""
    if dt is None:
        dt = datetime.datetime(2026, 5, 23, 14, 22, 8, 500000)
    return lambda: dt


def _make_plain(buf: io.StringIO, *, verbose: bool = False, times=None, wall=None, log_path=None):
    times = times or [0.0] * 50
    now = _fixed_now(times)
    wall_now = wall or _fixed_wall()
    return Renderer(buf, tty=False, verbose=verbose, log_path=log_path, now=now, wall_now=wall_now)


def _make_tty(buf: io.StringIO, *, verbose: bool = False, times=None, wall=None, log_path=None):
    times = times or [0.0] * 50
    now = _fixed_now(times)
    wall_now = wall or _fixed_wall()
    return Renderer(buf, tty=True, verbose=verbose, log_path=log_path, now=now, wall_now=wall_now)


# ---------------------------------------------------------------------------
# Fake Popen for consume() tests
# ---------------------------------------------------------------------------


class FakePopen:
    """A minimal Popen substitute backed by a string list of stdout lines."""

    def __init__(self, lines: list[str], returncode: int = 0):
        # Encode lines as the reader will call .rstrip("\n") etc.; keep as strings
        self.stdout = iter(lines)
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestPlainMode(unittest.TestCase):

    # 1. step_start emits nothing; step_end emits one line with glyph + duration
    def test_plain_mode_emits_one_line_per_step_end(self):
        buf = io.StringIO()
        r = _make_plain(buf, times=[100.0, 103.2, 200.0])
        h = r.step_start("apt update")      # consumes now() → 100.0
        r.step_end(h, "ok")                 # consumes now() → 103.2

        out = buf.getvalue()
        # step_start must produce no output
        # step_end must produce exactly one line containing the glyph and duration
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, f"Expected 1 line, got: {out!r}")
        line = lines[0]
        self.assertIn("✓", line)
        self.assertIn("apt update", line)
        self.assertIn("3.2s", line)

    # 2. fail dumps buffered raw lines below the step line
    def test_plain_mode_fail_dumps_buffer(self):
        buf = io.StringIO()
        r = _make_plain(buf, times=[0.0, 0.0, 0.0, 1.0])
        h = r.step_start("install foo")
        r.raw("a")
        r.raw("b")
        r.step_end(h, "fail")

        out = buf.getvalue()
        lines = out.splitlines()
        step_line = next((l for l in lines if "install foo" in l), None)
        self.assertIsNotNone(step_line, "No step line found")
        self.assertIn("✗", step_line)

        # Both raw lines should appear after the step line
        step_idx = lines.index(step_line)
        remaining = "\n".join(lines[step_idx + 1:])
        self.assertIn("a", remaining)
        self.assertIn("b", remaining)

    # 3. ok hides raw buffer
    def test_plain_mode_ok_hides_buffer(self):
        buf = io.StringIO()
        r = _make_plain(buf, times=[0.0, 0.0, 1.0])
        h = r.step_start("install bar")
        r.raw("hidden line")
        r.step_end(h, "ok")

        out = buf.getvalue()
        self.assertNotIn("hidden line", out)
        self.assertIn("✓", out)
        self.assertIn("install bar", out)

    # 4. skip includes detail
    def test_plain_mode_skip_includes_detail(self):
        buf = io.StringIO()
        r = _make_plain(buf, times=[0.0, 0.5])
        h = r.step_start("install baz")
        r.step_end(h, "skip", "already done")

        out = buf.getvalue()
        self.assertIn("↷", out)
        self.assertIn("already done", out)
        self.assertIn("install baz", out)

    # 5. verbose mode streams raw lines inline BEFORE the step end line
    def test_plain_mode_verbose_streams_raw(self):
        buf = io.StringIO()
        r = _make_plain(buf, verbose=True, times=[0.0, 0.0, 1.0])
        h = r.step_start("build")
        r.raw("hello")
        r.step_end(h, "ok")

        out = buf.getvalue()
        self.assertIn("hello", out)
        # hello must appear BEFORE the step end line
        hello_idx = out.index("hello")
        step_idx = out.index("✓")
        self.assertLess(hello_idx, step_idx, "raw 'hello' should appear before step end glyph")


class TestTtyMode(unittest.TestCase):

    # 6. TTY renders spinner + finalizes
    def test_tty_mode_renders_spinner_and_finalizes(self):
        buf = io.StringIO()
        r = _make_tty(buf, times=[0.0, 0.0, 1.0])
        h = r.step_start("apt update")   # draws initial spinner line
        r.step_end(h, "ok")

        out = buf.getvalue()
        # Must contain the ANSI clear sequence
        self.assertIn("\r\033[2K", out)
        # Must contain a spinner frame (any braille char)
        braille_found = any(c in out for c in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        self.assertTrue(braille_found, f"No spinner frame found in output: {out!r}")
        # Must contain finalized ✓ + name
        self.assertIn("✓", out)
        self.assertIn("apt update", out)

    # 7. nested step indents child by 2 spaces
    def test_tty_mode_nested_step_indents(self):
        buf = io.StringIO()
        # Provide enough time values for all now() calls throughout the sequence
        r = _make_tty(buf, times=[0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 2.0, 2.0])
        parent = r.step_start("provisioning", depth=0)
        child = r.step_start("apt update", depth=1)
        r.step_end(child, "ok")
        r.step_end(parent, "ok")

        out = buf.getvalue()
        # Child line should be indented by 2 spaces when drawn
        # Look for the indented child in the output
        self.assertIn("  ", out)  # at least some indentation
        self.assertIn("apt update", out)
        self.assertIn("provisioning", out)

        # Find lines that mention apt update; at least one should have leading spaces
        apt_segs = [seg for seg in out.split("\r\033[2K") if "apt update" in seg]
        self.assertTrue(
            any(seg.startswith("  ") for seg in apt_segs),
            f"No indented 'apt update' line found. Segments: {apt_segs!r}",
        )


class TestLogFile(unittest.TestCase):

    # 8. log file records start, raw, end
    def test_log_file_records_all_events(self):
        with _tmp_log() as log_path:
            buf = io.StringIO()
            r = _make_plain(buf, times=[0.0, 0.0, 1.0], log_path=log_path)
            h = r.step_start("test step")
            r.raw("some output")
            r.step_end(h, "ok")
            r.close()

            content = log_path.read_text()
            self.assertIn("start", content)
            self.assertIn("raw", content)
            self.assertIn("end", content)
            self.assertIn("test step", content)
            self.assertIn("some output", content)

    # 9. log file directory is created if it doesn't exist
    def test_log_file_directory_created(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "nested" / "deep" / "run.log"
            buf = io.StringIO()
            r = _make_plain(buf, times=[0.0, 1.0], log_path=log_path)
            h = r.step_start("x")
            r.step_end(h, "ok")
            r.close()
            self.assertTrue(log_path.exists(), "Log file should have been created")

    # 10. no errors when log_path=None
    def test_log_path_none_is_noop(self):
        buf = io.StringIO()
        r = _make_plain(buf, times=[0.0, 1.0], log_path=None)
        h = r.step_start("x")
        r.raw("line")
        r.step_end(h, "ok")
        r.close()  # Should not raise

    def test_close_is_idempotent(self):
        with _tmp_log() as log_path:
            buf = io.StringIO()
            r = _make_plain(buf, log_path=log_path)
            r.close()
            r.close()  # Second close should not raise


class TestConsume(unittest.TestCase):

    # 11. consume parses step markers and forwards raw lines
    def test_consume_parses_step_markers(self):
        lines = [
            "[step:start] apt update\n",
            "Reading package lists...\n",
            "[step:end] apt update ok\n",
            "[step:start] release foo\n",
            "[step:end] release foo skip sentinel\n",
        ]
        buf = io.StringIO()
        with _tmp_log() as log_path:
            r = _make_plain(buf, times=[0.0] * 20, log_path=log_path)
            proc = FakePopen(lines, returncode=0)
            rc = r.consume(proc, depth=1)
            r.close()

            self.assertEqual(rc, 0)

            log_content = log_path.read_text()

            # Check "apt update" start and end recorded
            self.assertIn("apt update", log_content)
            # Check "release foo" start and end recorded
            self.assertIn("release foo", log_content)
            # Check raw line recorded
            self.assertIn("Reading package lists...", log_content)

            # Check statuses: apt update should be ok, release foo should be skip
            # We look for "end" records
            end_lines = [l for l in log_content.splitlines() if " end " in l]
            apt_end = next((l for l in end_lines if "apt update" in l), None)
            foo_end = next((l for l in end_lines if "release foo" in l), None)
            self.assertIsNotNone(apt_end, "No end record for apt update")
            self.assertIsNotNone(foo_end, "No end record for release foo")
            self.assertIn("status=ok", apt_end)
            self.assertIn("status=skip", foo_end)
            self.assertIn("sentinel", foo_end)

    # 12. unterminated step is closed with fail/unterminated
    def test_consume_handles_unterminated_step(self):
        lines = [
            "[step:start] long running\n",
            "doing stuff\n",
            # EOF without end marker
        ]
        buf = io.StringIO()
        with _tmp_log() as log_path:
            r = _make_plain(buf, times=[0.0] * 20, log_path=log_path)
            proc = FakePopen(lines, returncode=1)
            rc = r.consume(proc, depth=1)
            r.close()

            log_content = log_path.read_text()
            end_lines = [l for l in log_content.splitlines() if " end " in l]
            lr_end = next((l for l in end_lines if "long running" in l), None)
            self.assertIsNotNone(lr_end, "No end record for unterminated step")
            self.assertIn("status=fail", lr_end)
            self.assertIn("unterminated", lr_end)

    # 13. mismatched end closes most-recent open step
    def test_consume_handles_mismatched_end(self):
        lines = [
            "[step:start] A\n",
            "[step:end] B ok\n",  # name mismatch — should close A
        ]
        buf = io.StringIO()
        with _tmp_log() as log_path:
            r = _make_plain(buf, times=[0.0] * 20, log_path=log_path)
            proc = FakePopen(lines, returncode=0)
            rc = r.consume(proc, depth=1)
            r.close()

            log_content = log_path.read_text()

            # A should have been closed (with whatever status)
            end_lines = [l for l in log_content.splitlines() if " end " in l]
            a_end = next((l for l in end_lines if "name=A" in l or " A " in l or "A depth" in l or "A status" in l), None)
            # More flexible: just check that an end record exists and step A was ended
            # The end record payload contains the step name
            a_ended = any("A" in l and " end " in l for l in log_content.splitlines())
            self.assertTrue(a_ended, f"Step A should have been closed. Log:\n{log_content}")

            # The mismatch warning should appear in the log (as a raw line)
            self.assertIn("mismatch", log_content)


# ---------------------------------------------------------------------------
# Context manager for temp log files
# ---------------------------------------------------------------------------

import contextlib
import tempfile
import os


@contextlib.contextmanager
def _tmp_log():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "run.log"


if __name__ == "__main__":
    unittest.main()
