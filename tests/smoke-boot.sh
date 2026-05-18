#!/usr/bin/env bash
# Smoke: VM is up, SSH-reachable, agent forwarding works, no host mounts leaked.
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME to the project/VM to test}"

status=$(limactl list -f '{{.Status}}' "$NAME")
[ "$status" = "Running" ] || { echo "VM $NAME not Running (got: $status)"; exit 1; }

limactl shell "$NAME" -- true

keys=$(limactl shell "$NAME" -- ssh-add -l 2>&1 || true)
echo "$keys" | grep -q -E '^(256|384|521|2048|3072|4096)' \
  || { echo "agent has no keys; got: $keys"; exit 1; }

mounts=$(limactl shell "$NAME" -- mount | grep -E '^\S+ on /Users' || true)
[ -z "$mounts" ] || { echo "host mounts detected: $mounts"; exit 1; }

echo "boot+agent OK"
