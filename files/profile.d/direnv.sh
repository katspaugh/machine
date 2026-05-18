# Sourced by bash login shells in the VM (/etc/profile.d/). Wires up direnv so
# project .envrc files (including `use op_env`) load on cd.
if command -v direnv >/dev/null 2>&1; then
  eval "$(direnv hook bash)"
fi
