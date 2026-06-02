#!/usr/bin/env bash
# Fake `machine` CLI for demo recording. Prints realistic-looking output.
set -e

cmd=$1
shift || true

slow() { printf '%s\n' "$1"; sleep "${2:-0.25}"; }

case "$cmd" in
  list)
    slow "NAME    STATUS     SSH                CPUS  MEMORY    DISK     DIR" 0.2
    slow "wallet  Running    127.0.0.1:60022    4     8GiB      30GiB    ~/.lima/wallet" 0.2
    slow "scraper Stopped    127.0.0.1:0        4     8GiB      30GiB    ~/.lima/scraper" 0.2
    slow "" 0.1
    slow "configured but not created: blog (run 'machine up <project>')" 0.2
    ;;
  up)
    project=${1:-wallet}
    slow "[machine] checking access to 3 repo(s)…" 0.6
    slow "INFO[0000] Attempting to download the image  arch=aarch64 (cached)" 0.5
    slow "INFO[0000] Using cache \"~/.cache/machine/base-arm64.img\"" 0.4
    slow "INFO[0001] [hostagent] Starting VZ (hint: to watch the boot progress, see \"~/.lima/$project/serial*.log\")" 0.5
    slow "INFO[0008] [hostagent] Waiting for the essential requirement 1 of 2: \"ssh\"" 0.6
    slow "INFO[0012] [hostagent] The essential requirement 1 of 2 is satisfied" 0.5
    slow "INFO[0013] READY. Run \`limactl shell $project\` to open the shell." 0.5
    slow "[clone] wavesurfer-react" 0.4
    slow "[clone] safe-wallet-monorepo" 0.4
    slow "[deps] yarn install" 0.6
    slow "[clone] safe-client-gateway: already present" 0.3
    slow "✓ $project ready — run 'machine ssh $project' to log in." 0.3
    ;;
  secrets)
    project=${1:-wallet}
    slow "[secrets] $project (wallet-dev)" 0.6
    slow "  → /run/user/501/dev-secrets/wallet-dev.env (tmpfs, 0600)" 0.4
    slow "synced 1 environment(s)" 0.3
    ;;
  ssh)
    project=${1:-wallet}
    prompt="katspaugh@$project:~/code/wallet\$ "
    printf '%s' "$prompt"; sleep 0.7
    printf 'node -v && docker -v\n'; sleep 0.4
    printf 'v22.11.0\n'; sleep 0.2
    printf 'Docker version 28.0.1, build a1b2c3d\n'; sleep 0.4
    printf '%s' "$prompt"; sleep 0.7
    printf 'claude --version\n'; sleep 0.4
    printf '2.1.3 (Claude Code)\n'; sleep 0.4
    printf '%s' "$prompt"; sleep 0.7
    printf 'gh auth status\n'; sleep 0.4
    printf 'github.com\n  ✓ Logged in as you (via SSH agent forward)\n'; sleep 0.5
    printf '%s' "$prompt"; sleep 0.6
    printf 'exit\n'
    ;;
  down)
    project=${1:-wallet}
    slow "INFO[0000] Stopping the instance \"$project\"" 0.6
    ;;
  *)
    echo "machine: unknown command '$cmd'"; exit 1;;
esac
