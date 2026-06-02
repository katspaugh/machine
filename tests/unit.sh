#!/usr/bin/env bash
# Unit tests for the host-side Python helpers in bin/machine.
# These don't require a VM; safe to run in CI.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests/unit -t . -p 'test_*.py' -v
