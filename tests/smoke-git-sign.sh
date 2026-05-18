#!/usr/bin/env bash
# Smoke: a fresh commit in the VM is signed by the forwarded SSH key, and the
# rendered allowed_signers file recognises it as "Good".
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

# shellcheck disable=SC2016  # single quotes intentional: script runs inside VM
limactl shell "$NAME" -- bash -lc '
  set -e
  workdir=$(mktemp -d)
  cd "$workdir"
  git init -q -b main
  echo hi > a
  git add a
  git commit -q -m "test"
  git log --show-signature -1 | grep -E "Good \"git\" signature" \
    || { git log --show-signature -1; exit 1; }
'

echo "git-sign OK"
