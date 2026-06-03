# bash completion for `machine`.
# Install:  source completions/machine.bash  (or drop into bash_completion.d)

_machine_projects() {
  local f="${PROJECTS_FILE:-$PWD/projects.toml}"
  [ -f "$f" ] || return 0
  python3 -c "import tomllib, sys
try: cfg = tomllib.loads(open('$f').read())
except Exception: sys.exit()
for n, v in cfg.items():
    if isinstance(v, dict): print(n)" 2>/dev/null
}

_machine() {
  local cur=${COMP_WORDS[COMP_CWORD]}
  local cmds="up down ssh claude tab run list destroy bake secrets init doctor"
  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=($(compgen -W "$cmds" -- "$cur"))
    return
  fi
  case "${COMP_WORDS[1]}" in
    up|down|ssh|claude|tab|run|secrets|destroy)
      COMPREPLY=($(compgen -W "$(_machine_projects)" -- "$cur")) ;;
    bake)
      COMPREPLY=($(compgen -W "--force" -- "$cur")) ;;
  esac
}
complete -F _machine machine
