# fish completion for `machine`.
# Install:  ln -s "$PWD/completions/machine.fish" ~/.config/fish/completions/machine.fish

function __machine_projects
    set -l projects_file (set -q PROJECTS_FILE; and echo $PROJECTS_FILE; or echo (pwd)/projects.toml)
    if test -f $projects_file
        python3 -c "import tomllib, sys
try: cfg = tomllib.loads(open('$projects_file').read())
except: sys.exit()
for n, v in cfg.items():
    if isinstance(v, dict): print(n)" 2>/dev/null
    end
end

set -l cmds up down ssh claude tab run list destroy bake secrets init doctor

complete -c machine -n "not __fish_seen_subcommand_from $cmds" -a "$cmds"

for c in up down ssh claude tab run secrets destroy
    complete -c machine -n "__fish_seen_subcommand_from $c" -a '(__machine_projects)'
end

complete -c machine -n "__fish_seen_subcommand_from destroy" -s y -l force -d "Skip confirmation"
complete -c machine -n "__fish_seen_subcommand_from bake" -l force -d "Rebuild even if cache is fresh"
complete -c machine -n "__fish_seen_subcommand_from secrets" -l clear -d "Wipe rendered secrets from VM tmpfs"
complete -c machine -n "__fish_seen_subcommand_from secrets" -l repo -d "Only this repo"
