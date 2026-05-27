# bash completion for `machine`.
# Install:  source completions/machine.bash         (one-off, current shell)
#           ln -s "$PWD/completions/machine.bash" /usr/local/etc/bash_completion.d/machine
#           # or `cat completions/machine.bash >> ~/.bashrc`

_machine_complete() {
  local cur prev words cword
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"

  local commands="list ps doctor validate up down ssh claude status destroy rebuild run secrets update config"

  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=($(compgen -W "$commands" -- "$cur"))
    return 0
  fi

  local cmd="${COMP_WORDS[1]}"
  case "$cmd" in
    up|down|ssh|claude|status|destroy|rebuild|run|secrets|update)
      # Project name: pull from projects.toml.
      local projects_file="${PROJECTS_FILE:-$PWD/projects.toml}"
      if [ -f "$projects_file" ]; then
        local names
        names=$(python3 - "$projects_file" <<'PY' 2>/dev/null
import sys, tomllib
try:
    cfg = tomllib.loads(open(sys.argv[1]).read())
except Exception:
    sys.exit(0)
for n, v in cfg.items():
    if n == "default_profile":
        continue
    if isinstance(v, dict):
        print(n)
PY
        )
        COMPREPLY=($(compgen -W "$names" -- "$cur"))
      fi
      ;;
    list|ps|doctor)
      COMPREPLY=($(compgen -W "--json" -- "$cur"))
      ;;
    config)
      COMPREPLY=($(compgen -W "add-project" -- "$cur"))
      ;;
  esac
}

complete -F _machine_complete machine
complete -F _machine_complete bin/machine
