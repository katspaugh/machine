"""Unit tests for provision/run.py. No VM required.

Run with: python3 -m unittest tests.unit.test_provision
   or:    bash tests/unit.sh
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def _load_run() -> object:
    """Import provision/run.py as a module without executing main()."""
    spec = importlib.util.spec_from_file_location(
        "provision_run", REPO / "provision" / "run.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["provision_run"] = mod
    spec.loader.exec_module(mod)
    return mod


run = _load_run()


class TestBlocks(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(run._blocks(None), [])

    def test_dict_wraps_to_single_item_list(self):
        self.assertEqual(run._blocks({"x": 1}), [{"x": 1}])

    def test_list_passes_through(self):
        self.assertEqual(run._blocks([{"x": 1}, {"y": 2}]), [{"x": 1}, {"y": 2}])

    def test_wrong_type_exits(self):
        with self.assertRaises(SystemExit):
            run._blocks(42)


class TestWhenOk(unittest.TestCase):
    def test_no_when_always_ok(self):
        self.assertTrue(run.when_ok({"packages": ["foo"]}, env={"arch": "arm64"}))

    def test_when_matches(self):
        self.assertTrue(
            run.when_ok({"when": {"arch": "arm64"}}, env={"arch": "arm64"})
        )

    def test_when_mismatch(self):
        self.assertFalse(
            run.when_ok({"when": {"arch": "amd64"}}, env={"arch": "arm64"})
        )

    def test_multiple_conditions_all_must_match(self):
        item = {"when": {"arch": "arm64", "codename": "noble"}}
        self.assertTrue(run.when_ok(item, env={"arch": "arm64", "codename": "noble"}))
        self.assertFalse(run.when_ok(item, env={"arch": "arm64", "codename": "jammy"}))


class TestLoadConfigs(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def _write(self, name: str, body: str) -> Path:
        p = Path(self.tmp) / name
        p.write_text(body)
        return p

    def test_single_file(self):
        a = self._write("a.toml", '[apt]\npackages = ["git", "curl"]\n')
        cfg = run.load_configs([a])
        self.assertEqual(cfg["apt"]["packages"], ["git", "curl"])

    def test_list_concat_across_files(self):
        a = self._write("a.toml", '[apt]\npackages = ["git"]\n')
        b = self._write("b.toml", '[apt]\npackages = ["curl"]\n')
        cfg = run.load_configs([a, b])
        # Both are tables with a `packages` list — the list inside merges.
        self.assertEqual(cfg["apt"]["packages"], ["git", "curl"])

    def test_top_level_list_concat(self):
        a = self._write("a.toml", '[[apt]]\npackages = ["git"]\n')
        b = self._write("b.toml", '[[apt]]\npackages = ["curl"]\n')
        cfg = run.load_configs([a, b])
        self.assertEqual(len(cfg["apt"]), 2)
        self.assertEqual(cfg["apt"][0]["packages"], ["git"])
        self.assertEqual(cfg["apt"][1]["packages"], ["curl"])

    def test_scalar_first_writer_wins(self):
        a = self._write(
            "a.toml",
            '[claude]\nmarketplace = "base"\ndefault_permission_mode = "auto"\n',
        )
        b = self._write(
            "b.toml",
            '[claude]\ndefault_permission_mode = "bypassPermissions"\n',
        )
        cfg = run.load_configs([a, b])
        # First-writer-wins: base config locks the permission mode so a profile
        # can't accidentally weaken security defaults.
        self.assertEqual(cfg["claude"]["default_permission_mode"], "auto")
        self.assertEqual(cfg["claude"]["marketplace"], "base")

    def test_unrelated_keys_merge(self):
        a = self._write("a.toml", '[apt]\npackages = ["git"]\n')
        b = self._write("b.toml", '[corepack]\nprepare = ["pnpm@latest"]\n')
        cfg = run.load_configs([a, b])
        self.assertEqual(cfg["apt"]["packages"], ["git"])
        self.assertEqual(cfg["corepack"]["prepare"], ["pnpm@latest"])


class TestDetectUser(unittest.TestCase):
    def test_uses_sudo_user(self):
        import os
        old = os.environ.get("SUDO_USER")
        os.environ["SUDO_USER"] = "ubuntu"
        try:
            self.assertEqual(run.detect_user(), "ubuntu")
        finally:
            if old is None:
                del os.environ["SUDO_USER"]
            else:
                os.environ["SUDO_USER"] = old

    def test_exits_when_sudo_user_unset(self):
        import os
        old = os.environ.get("SUDO_USER")
        os.environ.pop("SUDO_USER", None)
        try:
            with self.assertRaises(SystemExit):
                run.detect_user()
        finally:
            if old is not None:
                os.environ["SUDO_USER"] = old

    def test_exits_when_sudo_user_root(self):
        import os
        old = os.environ.get("SUDO_USER")
        os.environ["SUDO_USER"] = "root"
        try:
            with self.assertRaises(SystemExit):
                run.detect_user()
        finally:
            if old is None:
                del os.environ["SUDO_USER"]
            else:
                os.environ["SUDO_USER"] = old


class TestIdempotentClaudeCmd(unittest.TestCase):
    def test_builds_shell_string(self):
        s = run._idempotent_claude_cmd("plugin install foo")
        self.assertIn("claude plugin install foo", s)
        self.assertIn("grep -qi", s)


if __name__ == "__main__":
    unittest.main()
