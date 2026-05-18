#!/usr/bin/env bash
# Smoke: docker daemon is up and `docker run hello-world` succeeds.
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

limactl shell "$NAME" -- docker version >/dev/null
out=$(limactl shell "$NAME" -- docker run --rm hello-world 2>&1)
echo "$out" | grep -q 'Hello from Docker!' || { echo "$out"; exit 1; }
echo "docker OK"
