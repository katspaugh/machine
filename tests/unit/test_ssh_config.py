"""Unit tests for the SSH config helpers in bin/machine."""
from __future__ import annotations

import unittest

from .test_machine import m  # reuses the bin/machine importer


class TestHostAlias(unittest.TestCase):
    def test_lowercase_passthrough(self):
        self.assertEqual(m.host_alias("blog"), "machine-blog")

    def test_hyphens_preserved(self):
        self.assertEqual(m.host_alias("my-app"), "machine-my-app")

    def test_digits_allowed(self):
        self.assertEqual(m.host_alias("a1"), "machine-a1")

    def test_non_alnum_becomes_dash(self):
        # Project keys are already validated by validate_name(), so we don't
        # see uppercase or whitespace here; but underscores etc. would be
        # sanitized if they ever leak in.
        self.assertEqual(m.host_alias("a_b.c"), "machine-a-b-c")


class TestParseLimaSshOptions(unittest.TestCase):
    def test_parses_quoted_and_unquoted(self):
        out = (
            'IdentityFile="/Users/example/.lima/_config/user"\n'
            "User=example.linux\n"
            "Hostname=127.0.0.1\n"
            "Port=60022\n"
            "StrictHostKeyChecking=no\n"
        )
        got = m.parse_lima_ssh_options(out)
        self.assertEqual(got["IdentityFile"], "/Users/example/.lima/_config/user")
        self.assertEqual(got["User"], "example.linux")
        self.assertEqual(got["Hostname"], "127.0.0.1")
        self.assertEqual(got["Port"], "60022")

    def test_ignores_blank_and_comments(self):
        out = "\n# comment\nUser=bob\n   \n"
        self.assertEqual(m.parse_lima_ssh_options(out), {"User": "bob"})

    def test_value_with_equals_sign(self):
        # ProxyCommand-like values can contain '=' inside.
        out = 'ProxyCommand=ssh -W %h:%p user=foo bastion\n'
        self.assertEqual(
            m.parse_lima_ssh_options(out)["ProxyCommand"],
            "ssh -W %h:%p user=foo bastion",
        )

    def test_empty_input(self):
        self.assertEqual(m.parse_lima_ssh_options(""), {})


class TestRenderBlock(unittest.TestCase):
    def _opts(self, port: str) -> dict:
        return {
            "Hostname": "127.0.0.1",
            "Port": port,
            "User": "user.linux",
            "IdentityFile": "/Users/u/.lima/_config/user",
        }

    def test_empty_entries_returns_empty_string(self):
        self.assertEqual(m.render_block([]), "")

    def test_single_entry(self):
        got = m.render_block([("blog", self._opts("60123"))])
        expected = (
            f"{m.SSH_SENTINEL_OPEN}\n"
            "Host machine-blog\n"
            "    HostName 127.0.0.1\n"
            "    Port 60123\n"
            "    User user.linux\n"
            "    IdentityFile /Users/u/.lima/_config/user\n"
            "    IdentitiesOnly yes\n"
            "    StrictHostKeyChecking no\n"
            "    UserKnownHostsFile /dev/null\n"
            "    ForwardAgent yes\n"
            f"{m.SSH_SENTINEL_CLOSE}\n"
        )
        self.assertEqual(got, expected)

    def test_multiple_entries_separated_by_blank_line(self):
        got = m.render_block([
            ("blog", self._opts("60123")),
            ("wallet", self._opts("60127")),
        ])
        # exactly one blank line between the two Host blocks
        self.assertIn("ForwardAgent yes\n\nHost machine-wallet\n", got)
        self.assertTrue(got.startswith(m.SSH_SENTINEL_OPEN + "\n"))
        self.assertTrue(got.endswith(m.SSH_SENTINEL_CLOSE + "\n"))

    def test_entries_use_host_alias_sanitization(self):
        got = m.render_block([("my_proj.x", self._opts("60001"))])
        self.assertIn("Host machine-my-proj-x\n", got)

    def test_missing_option_is_omitted(self):
        # If Lima didn't report a field (shouldn't happen in practice),
        # render_block must not crash and must skip that line.
        partial = {"Hostname": "127.0.0.1", "Port": "60001"}
        got = m.render_block([("p", partial)])
        self.assertIn("HostName 127.0.0.1", got)
        self.assertIn("Port 60001", got)
        self.assertNotIn("User ", got)
        self.assertNotIn("IdentityFile ", got)


class TestSpliceBlock(unittest.TestCase):
    def _block(self, body: str = "Host machine-blog\n    Port 60022\n") -> str:
        return f"{m.SSH_SENTINEL_OPEN}\n{body}{m.SSH_SENTINEL_CLOSE}\n"

    def test_empty_existing_block_only(self):
        new = self._block()
        self.assertEqual(m.splice_block("", new), new)

    def test_existing_no_block_appends_with_blank_line(self):
        existing = "Host foo\n    HostName 1.2.3.4\n"
        new = self._block()
        got = m.splice_block(existing, new)
        # original content preserved verbatim, then one blank line, then block.
        self.assertEqual(got, existing + "\n" + new)

    def test_existing_no_block_no_trailing_newline(self):
        existing = "Host foo\n    HostName 1.2.3.4"  # no trailing newline
        new = self._block()
        got = m.splice_block(existing, new)
        # the original is preserved, exactly one blank line separates.
        self.assertEqual(got, existing + "\n\n" + new)

    def test_replaces_existing_block(self):
        old_block = self._block("Host machine-old\n    Port 60011\n")
        new_block = self._block("Host machine-new\n    Port 60022\n")
        existing = "Host foo\n    HostName 1.2.3.4\n\n" + old_block
        got = m.splice_block(existing, new_block)
        self.assertEqual(got, "Host foo\n    HostName 1.2.3.4\n\n" + new_block)

    def test_replaces_block_in_middle(self):
        old_block = self._block("Host machine-old\n    Port 60011\n")
        new_block = self._block("Host machine-new\n    Port 60022\n")
        suffix = "\nHost bar\n    HostName 5.6.7.8\n"
        existing = "Host foo\n\n" + old_block + suffix
        got = m.splice_block(existing, new_block)
        self.assertEqual(got, "Host foo\n\n" + new_block + suffix)

    def test_empty_new_block_removes_existing(self):
        existing = "Host foo\n    HostName 1.2.3.4\n\n" + self._block()
        got = m.splice_block(existing, "")
        # No trailing blank-line orphan.
        self.assertEqual(got, "Host foo\n    HostName 1.2.3.4\n")

    def test_empty_new_block_no_existing_is_noop(self):
        existing = "Host foo\n    HostName 1.2.3.4\n"
        self.assertEqual(m.splice_block(existing, ""), existing)

    def test_duplicate_open_sentinels_raises(self):
        existing = self._block() + "\n" + self._block()
        with self.assertRaises(m.DuplicateSentinelError):
            m.splice_block(existing, self._block("Host x\n"))

    def test_only_close_sentinel_raises(self):
        existing = f"random\n{m.SSH_SENTINEL_CLOSE}\nmore\n"
        with self.assertRaises(m.DuplicateSentinelError):
            m.splice_block(existing, self._block("Host x\n"))

    def test_only_open_sentinel_raises(self):
        existing = f"{m.SSH_SENTINEL_OPEN}\nrandom\n"
        with self.assertRaises(m.DuplicateSentinelError):
            m.splice_block(existing, self._block("Host x\n"))


if __name__ == "__main__":
    unittest.main()
