#!/usr/bin/env bash
# Unit tests for the host-side Python helpers in provision/run.py.
# These don't require a VM; safe to run in CI.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests/unit -p 'test_*.py' -v
