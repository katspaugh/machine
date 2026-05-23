"""Unit tests for the [step:*] protocol markers emitted by provision/run.py.

Run with: python3 -m unittest tests.unit.test_provision_protocol
   or:    bash tests/unit.sh
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PROVISION_TOML = REPO / "provision.toml"
RUN_PY = REPO / "provision" / "run.py"


def _dry_run_stderr() -> str:
    """Invoke provision/run.py --dry-run and return the stderr output."""
    env = {**os.environ, "SUDO_USER": "testuser"}
    result = subprocess.run(
        [sys.executable, str(RUN_PY), "--dry-run", str(PROVISION_TOML)],
        capture_output=True,
        text=True,
        env=env,
    )
    # Dry-run should always succeed (exit 0).
    assert result.returncode == 0, (
        f"dry-run exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result.stderr


class TestDryRunEmitsStepMarkers(unittest.TestCase):
    """Every [step:start] must be matched by exactly one [step:end] with the
    same name, with no intervening unmatched start at the same scope."""

    @classmethod
    def setUpClass(cls):
        cls.stderr = _dry_run_stderr()
        cls.lines = cls.stderr.splitlines()

    def _step_lines(self):
        return [l for l in self.lines if l.startswith("[step:")]

    def test_every_start_has_matching_end(self):
        """For every [step:start] <name> there must be a [step:end] <name> ..."""
        started: list[str] = []
        for line in self._step_lines():
            if line.startswith("[step:start] "):
                name = line[len("[step:start] "):]
                started.append(name)
            elif line.startswith("[step:end] "):
                rest = line[len("[step:end] "):]
                # rest = "<name> ok|skip ...|fail ..."
                # Name ends at the last space before status word.
                parts = rest.rsplit(" ", 1)
                # The status is the last token (could be "ok", a reason word,
                # or an exit-code digit). The name is everything before.
                # But "skip <reason>" has two trailing tokens. We need to strip
                # the status keyword off. Status words: ok, fail, skip.
                tokens = rest.split(" ")
                # Find where the name ends: status starts at the first token
                # that is 'ok', 'skip', or 'fail' *after* position 0.
                status_idx = None
                for i, t in enumerate(tokens):
                    if t in ("ok", "skip", "fail") and i > 0:
                        status_idx = i
                        break
                self.assertIsNotNone(
                    status_idx,
                    f"Cannot parse status from [step:end] line: {line!r}",
                )
                name = " ".join(tokens[:status_idx])
                self.assertIn(
                    name,
                    started,
                    f"[step:end] for {name!r} but no matching [step:start]",
                )
                started.remove(name)
        self.assertEqual(
            started,
            [],
            f"[step:start] markers without matching [step:end]: {started}",
        )

    def test_apt_update_markers_present(self):
        """apt update must appear as a start+end pair."""
        step_lines = self._step_lines()
        starts = [l for l in step_lines if l == "[step:start] apt update"]
        ends = [l for l in step_lines if l.startswith("[step:end] apt update ")]
        self.assertGreater(len(starts), 0, "No [step:start] apt update found")
        self.assertEqual(len(starts), len(ends), "apt update start/end count mismatch")

    def test_claude_marketplace_markers_present(self):
        """claude marketplace must appear as a start+end pair."""
        step_lines = self._step_lines()
        starts = [l for l in step_lines if l == "[step:start] claude marketplace"]
        ends = [l for l in step_lines if l.startswith("[step:end] claude marketplace ")]
        self.assertGreater(len(starts), 0, "No [step:start] claude marketplace found")
        self.assertEqual(len(starts), len(ends), "claude marketplace start/end count mismatch")

    def test_installer_markers_present(self):
        """At least one install <name> pair must appear (provision.toml has [[installer]])."""
        step_lines = self._step_lines()
        starts = [l for l in step_lines if l.startswith("[step:start] install ")]
        ends = [l for l in step_lines if l.startswith("[step:end] install ")]
        self.assertGreater(len(starts), 0, "No [step:start] install ... found")
        self.assertEqual(len(starts), len(ends), "install start/end count mismatch")


class TestStepNamesHaveNoNewlines(unittest.TestCase):
    """No [step:start] or [step:end] line may contain an embedded newline
    within the name portion (i.e. more than one newline character total in
    the line is prohibited; the one at EOL is not captured by splitlines)."""

    @classmethod
    def setUpClass(cls):
        cls.stderr = _dry_run_stderr()
        cls.lines = cls.stderr.splitlines()

    def test_no_embedded_newlines_in_step_lines(self):
        """splitlines() already breaks on \\n, so each element must not
        contain \\n, \\r, or \\x0b etc."""
        for line in self.lines:
            if not (line.startswith("[step:start] ") or line.startswith("[step:end] ")):
                continue
            for ch in ("\n", "\r", "\x0b", "\x0c"):
                self.assertNotIn(
                    ch,
                    line,
                    f"Step marker line contains embedded newline char {ch!r}: {line!r}",
                )


if __name__ == "__main__":
    unittest.main()
