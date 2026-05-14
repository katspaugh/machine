# Installed by `machine` provisioning. Edit files/fish/config.fish and re-provision.
# Fish ships with sensible defaults (prompt, history, completions); we only
# add the integrations the VM cares about.

if status is-interactive
    # direnv
    if command -q direnv
        direnv hook fish | source
    end

    # Aliases (abbreviations expand inline so they're visible in history).
    abbr -a g   git
    abbr -a gs  git status
    abbr -a gd  git diff
    abbr -a gl  git log --oneline --graph --decorate
    abbr -a ll  ls -lah
    abbr -a la  ls -A

    # fd-find ships as `fdfind` on Debian/Ubuntu.
    if command -q fdfind; and not command -q fd
        alias fd=fdfind
    end
end
