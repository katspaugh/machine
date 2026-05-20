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


if __name__ == "__main__":
    unittest.main()
