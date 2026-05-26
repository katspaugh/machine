"""Tests for the JSON output of `machine doctor --json`."""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
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


class TestDoctorCollector(unittest.TestCase):
    def test_ok_records_pass(self):
        c = m.DoctorCollector(json_mode=True)
        c.ok("limactl on PATH")
        self.assertEqual(c.results, [
            {"name": "limactl on PATH", "status": "ok", "detail": None, "hint": None},
        ])

    def test_ok_with_detail(self):
        c = m.DoctorCollector(json_mode=True)
        c.ok("git user.name", detail="Jane Doe")
        self.assertEqual(c.results[0]["detail"], "Jane Doe")

    def test_fail_with_hint(self):
        c = m.DoctorCollector(json_mode=True)
        c.fail("SSH_AUTH_SOCK unset", hint="load a key with ssh-add")
        self.assertEqual(c.results, [
            {"name": "SSH_AUTH_SOCK unset", "status": "fail",
             "detail": None, "hint": "load a key with ssh-add"},
        ])

    def test_summary_counts(self):
        c = m.DoctorCollector(json_mode=True)
        c.ok("a"); c.ok("b"); c.fail("c")
        self.assertEqual(c.summary(), {"checks": 3, "fails": 1})

    def test_json_mode_silent(self):
        """In json_mode, ok/fail/section do not print to stdout/stderr."""
        c = m.DoctorCollector(json_mode=True)
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out, \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            c.section("host")
            c.ok("a")
            c.fail("b", hint="fix it")
            c.warn("watch out")
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

    def test_prose_mode_prints(self):
        c = m.DoctorCollector(json_mode=False)
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out, \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            c.section("host")
            c.ok("a")
            c.fail("b", hint="fix it")
        self.assertIn("[doctor] host", out.getvalue())
        self.assertIn("  ok  a", out.getvalue())
        self.assertIn("FAIL b", err.getvalue())
        self.assertIn("hint: fix it", err.getvalue())


class TestCmdDoctorJson(unittest.TestCase):
    """End-to-end: `cmd_doctor(--json)` returns a single valid JSON object."""

    def _patched_stack(self, stack: contextlib.ExitStack) -> None:
        stack.enter_context(mock.patch.object(
            m, "git_config",
            side_effect=lambda k: {"user.name": "Jane Doe",
                                   "user.email": "jane@example.com"}.get(k)))
        stack.enter_context(mock.patch.object(
            m, "read_signing_key", return_value="ssh-ed25519 AAAA..."))
        stack.enter_context(mock.patch.dict(
            os.environ, {"SSH_AUTH_SOCK": "/tmp/agent"}, clear=False))
        stack.enter_context(mock.patch.object(
            m, "doctor_ssh_config", lambda c: None))
        stack.enter_context(mock.patch(
            "subprocess.run",
            return_value=mock.Mock(returncode=0,
                                   stdout="256 SHA256:abc user@host (ED25519)\n")))
        stack.enter_context(mock.patch.object(
            m, "PROJECTS_FILE", REPO / "projects.toml.example"))
        stack.enter_context(mock.patch(
            "shutil.which", return_value="/usr/local/bin/limactl"))

    def test_json_shape(self):
        with contextlib.ExitStack() as stack:
            self._patched_stack(stack)
            out = stack.enter_context(
                mock.patch("sys.stdout", new_callable=io.StringIO))
            rc = m.cmd_doctor(argparse.Namespace(json=True))
        payload = json.loads(out.getvalue())
        self.assertIn("checks", payload)
        self.assertIn("summary", payload)
        self.assertIsInstance(payload["checks"], list)
        for c in payload["checks"]:
            self.assertEqual(set(c.keys()), {"name", "status", "detail", "hint"})
            self.assertIn(c["status"], {"ok", "fail"})
        self.assertEqual(payload["summary"]["checks"], len(payload["checks"]))
        self.assertEqual(payload["summary"]["fails"],
                         sum(1 for c in payload["checks"] if c["status"] == "fail"))
        if payload["summary"]["fails"] == 0:
            self.assertEqual(rc, 0)
        else:
            self.assertEqual(rc, 1)

    def test_no_json_flag_prints_prose(self):
        with contextlib.ExitStack() as stack:
            self._patched_stack(stack)
            out = stack.enter_context(
                mock.patch("sys.stdout", new_callable=io.StringIO))
            m.cmd_doctor(argparse.Namespace(json=False))
        s = out.getvalue()
        self.assertIn("[doctor] host", s)
        self.assertIn("  ok  ", s)


if __name__ == "__main__":
    unittest.main()
