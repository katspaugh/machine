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


if __name__ == "__main__":
    unittest.main()
