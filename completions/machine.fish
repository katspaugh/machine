# fish completion for `machine`.
# Install:  ln -s "$PWD/completions/machine.fish" ~/.config/fish/completions/machine.fish

function __machine_projects
    set -l projects_file (set -q PROJECTS_FILE; and echo $PROJECTS_FILE; or echo (pwd)/projects.toml)
    if test -f $projects_file
        python3 -c "import tomllib, sys
try: cfg = tomllib.loads(open('$projects_file').read())
except: sys.exit()
for n, v in cfg.items():
    if n != 'default_profile' and isinstance(v, dict): print(n)" 2>/dev/null
    end
end

set -l cmds list ps doctor validate up down ssh status destroy rebuild run secrets claude-login claude-logout update

complete -c machine -n "not __fish_seen_subcommand_from $cmds" -a "$cmds"

for c in up down ssh status destroy rebuild run secrets claude-login claude-logout update
    complete -c machine -n "__fish_seen_subcommand_from $c" -a '(__machine_projects)'
end

complete -c machine -n "__fish_seen_subcommand_from up rebuild" -l dry-run -d "Print provision steps without executing"
complete -c machine -n "__fish_seen_subcommand_from destroy rebuild" -s y -l force -d "Skip confirmation"
complete -c machine -n "__fish_seen_subcommand_from update" -l reprovision -d "Re-apply TOML provisioning"
complete -c machine -n "__fish_seen_subcommand_from secrets" -l clear -d "Wipe rendered secrets from VM tmpfs"
