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
        dt = datetime.datetime(2026, 5, 23, 14, 22, 8, 500000, tzinfo=datetime.timezone.utc)
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


class _ErrAfterFirstIter:
    """An iterator that yields one item then raises IOError."""

    def __init__(self, first: str):
        self._first = first
        self._done = False

    def __iter__(self):
        return self

    def __next__(self):
        if not self._done:
            self._done = True
            return self._first
        raise IOError("simulated stream disconnect")


class FakeErrPopen:
    """A minimal Popen substitute whose stdout raises IOError after one line."""

    def __init__(self, first_line: str):
        self.stdout = _ErrAfterFirstIter(first_line)

    def wait(self) -> int:
        return 1


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
        self.assertIn("apt update", out)
        self.assertIn("provisioning", out)

        # The finalized child line must be exactly "  ✓ apt update" (2-space indent).
        # Split on the ANSI clear sequence to isolate individual drawn lines.
        segments = out.split("\r\033[2K")
        finalized_child = next(
            (seg for seg in segments if "apt update" in seg and "✓" in seg),
            None,
        )
        self.assertIsNotNone(finalized_child, f"No finalized child line found in segments: {segments!r}")
        # Strip a leading \r if present (from ANSI_CR before ANSI_CLEAR_LINE)
        text = finalized_child.lstrip("\r")
        self.assertTrue(
            text.startswith("  ✓"),
            f"Expected child line to start with '  ✓' (2 spaces), got: {text!r}",
        )
        self.assertFalse(
            text.startswith("   ✓"),
            f"Child line has too much indentation: {text!r}",
        )

    # 8. TTY fail dumps buffered raw lines below the step line
    def test_tty_mode_fail_dumps_buffer(self):
        buf = io.StringIO()
        r = _make_tty(buf, times=[0.0, 0.0, 0.0, 1.0])
        h = r.step_start("build")
        r.raw("err line")
        r.step_end(h, "fail", "exit 2")

        out = buf.getvalue()
        # Must contain the failure glyph
        self.assertIn("✗", out)
        # Must contain the detail
        self.assertIn("exit 2", out)
        # Must contain the buffered raw line (indented)
        self.assertIn("err line", out)
        # The raw line must appear after the finalized step line
        fail_idx = out.index("✗")
        raw_idx = out.index("err line")
        self.assertGreater(raw_idx, fail_idx, "raw line should appear after the fail glyph")

    # 9. TTY verbose mode streams raw lines while a step is active
    def test_tty_mode_verbose_streams_raw(self):
        buf = io.StringIO()
        r = _make_tty(buf, verbose=True, times=[0.0] * 20)
        h = r.step_start("build")
        r.raw("hello")
        r.step_end(h, "ok")

        out = buf.getvalue()
        self.assertIn("hello", out)
        # hello must appear before the finalized ✓
        hello_idx = out.index("hello")
        ok_idx = out.index("✓")
        self.assertLess(hello_idx, ok_idx, "raw 'hello' should appear before the step-end glyph")

    # 10. TTY skip includes detail in finalized line
    def test_tty_mode_skip_includes_detail(self):
        buf = io.StringIO()
        r = _make_tty(buf, times=[0.0] * 20)
        h = r.step_start("install pkg")
        r.step_end(h, "skip", "already done")

        out = buf.getvalue()
        self.assertIn("↷", out)
        self.assertIn("install pkg", out)
        self.assertIn("already done", out)


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

    # 13. mismatched end closes most-recent open step with fixed fail+mismatch detail
    def test_consume_handles_mismatched_end(self):
        lines = [
            "[step:start] A\n",
            "[step:end] B ok\n",  # name mismatch — should close A, NOT use B's status
        ]
        buf = io.StringIO()
        with _tmp_log() as log_path:
            r = _make_plain(buf, times=[0.0] * 20, log_path=log_path)
            proc = FakePopen(lines, returncode=0)
            rc = r.consume(proc, depth=1)
            r.close()

            log_content = log_path.read_text()

            # A must have been closed
            a_ended = any("A" in l and " end " in l for l in log_content.splitlines())
            self.assertTrue(a_ended, f"Step A should have been closed. Log:\n{log_content}")

            # The innocent step A must be closed with status=fail (NOT ok from B)
            end_lines = [l for l in log_content.splitlines() if " end " in l and "A" in l]
            self.assertTrue(
                any("status=fail" in l for l in end_lines),
                f"Step A should be closed with status=fail. End lines: {end_lines}",
            )

            # The detail must contain "mismatch" (not B's original detail)
            self.assertTrue(
                any("mismatch" in l for l in end_lines),
                f"Step A's detail should contain 'mismatch'. End lines: {end_lines}",
            )

            # The mismatch warning should also appear in the log as a raw line
            self.assertIn("mismatch", log_content)

    # 14. greedy regex: step name with embedded space+ok is resolved correctly
    def test_consume_greedy_end_name(self):
        lines = [
            "[step:start] check ok-results\n",
            "[step:end] check ok-results ok\n",
        ]
        buf = io.StringIO()
        with _tmp_log() as log_path:
            r = _make_plain(buf, times=[0.0] * 20, log_path=log_path)
            proc = FakePopen(lines, returncode=0)
            r.consume(proc, depth=1)
            r.close()

            log_content = log_path.read_text()
            end_lines = [l for l in log_content.splitlines() if " end " in l]
            # The step "check ok-results" must be closed successfully — not "check"
            named_end = next(
                (l for l in end_lines if "check ok-results" in l),
                None,
            )
            self.assertIsNotNone(
                named_end,
                f"Expected 'check ok-results' in an end record; got: {end_lines}",
            )
            self.assertIn("status=ok", named_end)

    # 15. stream exception still finalizes open steps
    def test_consume_finalizes_on_stream_exception(self):
        buf = io.StringIO()
        with _tmp_log() as log_path:
            r = _make_plain(buf, times=[0.0] * 20, log_path=log_path)
            proc = FakeErrPopen("[step:start] foo\n")
            try:
                r.consume(proc, depth=1)
            except IOError:
                pass  # exception may propagate — cleanup must still have run
            r.close()

            log_content = log_path.read_text()
            end_lines = [l for l in log_content.splitlines() if " end " in l]
            foo_end = next((l for l in end_lines if "foo" in l), None)
            self.assertIsNotNone(foo_end, f"Step 'foo' must be finalized. Log:\n{log_content}")
            self.assertIn("status=fail", foo_end)
            self.assertIn("unterminated", foo_end)

            # Renderer's internal stack must be empty
            self.assertEqual(r._stack, [], "Renderer stack must be empty after cleanup")


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
