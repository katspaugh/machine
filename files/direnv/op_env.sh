#!/usr/bin/env bash
# direnv stdlib extension: loads a cached 1Password Environment from
# $XDG_RUNTIME_DIR/dev-secrets/<env-id>.env, populated on the host by
# `bin/machine secrets <project>`. The cache is keyed by Environment ID (a
# UUID), not by project name, so two projects sharing an Environment also
# share the cache.
#
# Usage in .envrc:  use op_env <environment-id>
# Find the ID in 1Password desktop: Developer → Environments → Manage → Copy ID.

use_op_env() {
  local env_id="${1:?op_env: 1Password Environment ID required (find in Developer → Environments)}"
  local secrets_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/dev-secrets"
  local cache="$secrets_dir/$env_id.env"

  if [ ! -r "$cache" ]; then
    log_error "op_env: $cache not found"
    log_error "  Run on the host:  bin/machine secrets $(basename "$(dirname "$PWD")")"
    return 1
  fi

  dotenv "$cache"
  watch_file "$cache"
}
