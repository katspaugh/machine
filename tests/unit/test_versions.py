"""Release-version agreement between flake.nix and Formula/machine.rb.

scripts/release.sh bumps both in one release run and pushes them to main in a
single push, so on any commit CI sees they must agree. A hand-edit to either
file that drifts the versions fails here (in CI and in the release preflight).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestVersionAgreement(unittest.TestCase):
    def test_formula_tag_matches_flake_version(self):
        flake = (ROOT / "flake.nix").read_text()
        flake_match = re.search(r'^\s*version = "(\d+\.\d+\.\d+)";', flake, re.M)
        self.assertIsNotNone(flake_match, "flake.nix: no version = \"X.Y.Z\" line")

        formula = (ROOT / "Formula" / "machine.rb").read_text()
        url_match = re.search(r"archive/refs/tags/v(\d+\.\d+\.\d+)\.tar\.gz", formula)
        self.assertIsNotNone(url_match, "Formula/machine.rb: no tagged-tarball url")

        self.assertEqual(
            url_match.group(1), flake_match.group(1),
            "Formula/machine.rb pins a different version than flake.nix — "
            "run scripts/release.sh instead of editing versions by hand",
        )
