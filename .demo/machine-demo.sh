#!/usr/bin/env bash
# Fake `machine` CLI for demo recording. Prints realistic-looking output.
set -e

cmd=$1
shift || true

slow() { printf '%s\n' "$1"; sleep "${2:-0.25}"; }

case "$cmd" in
  list)
    slow "blog        repos=1  profiles=[]"
    slow "wallet      repos=3  profiles=[cypress]"
    slow "playground  repos=1  profiles=[cypress, supabase-fly]"
    ;;
  up)
    project=$1
    slow "→ creating VM '$project' from lima.yaml" 0.4
    slow "  limactl create --name=$project lima.yaml ... ok" 0.5
    slow "→ starting VM" 0.3
    slow "  limactl start $project ......................... ok" 0.8
    slow "→ pushing provisioner + profiles" 0.3
    slow "  rsync /opt/dev-vm/ .............................. ok" 0.4
    slow "→ provisioning (base + cypress)" 0.3
    slow "  [apt] docker-ce, nodejs, gh, git ................ ok" 0.5
    slow "  [npm] @anthropic-ai/claude-code, @openai/codex .. ok" 0.5
    slow "  [claude] plugins: superpowers, frontend-design .. ok" 0.5
    slow "  [profile:cypress] chrome + cypress libs ......... ok" 0.5
    slow "→ cloning repos into ~/code/" 0.3
    slow "  git@github.com:you/wallet.git ................... ok" 0.4
    slow "  yarn install ..................................... ok" 0.5
    slow "✓ $project ready" 0.3
    ;;
  ssh)
    project=$1
    prompt="katspaugh@$project:~/code/wallet$ "
    printf '%s' "$prompt"; sleep 0.7
    printf 'node -v && docker -v\n'; sleep 0.4
    printf 'v22.11.0\n'; sleep 0.2
    printf 'Docker version 28.0.1, build a1b2c3d\n'; sleep 0.4
    printf '%s' "$prompt"; sleep 0.7
    printf 'claude --version\n'; sleep 0.4
    printf '2.0.41 (Claude Code)\n'; sleep 0.4
    printf '%s' "$prompt"; sleep 0.7
    printf 'gh auth status\n'; sleep 0.4
    printf 'github.com\n  ✓ Logged in as you (via SSH agent forward)\n'; sleep 0.5
    printf '%s' "$prompt"; sleep 0.6
    printf 'exit\n'
    ;;
  status)
    slow "NAME      STATUS     SSH         ARCH      CPUS  MEMORY"
    slow "wallet    Running    127.0.0.1   aarch64   4     8GiB"
    ;;
  secrets)
    project=$1
    slow "→ reading 1Password environments referenced in $project" 0.3
    slow "  wallet/.envrc → op env: wallet-dev .............. ok (Touch ID)" 0.6
    slow "  → /run/user/1000/dev-secrets/wallet-dev.env (tmpfs, 0600)" 0.3
    slow "✓ secrets synced" 0.2
    ;;
  down)
    slow "→ stopping VM '$1' ................................ ok" 0.5
    ;;
  *)
    echo "machine: unknown command '$cmd'"; exit 1;;
esac
