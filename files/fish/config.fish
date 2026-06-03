# Installed by `machine` provisioning. Edit files/fish/config.fish and re-provision.
# Fish ships with sensible defaults (prompt, history, completions); we only
# add the integrations the VM cares about.

# Fish does NOT source /etc/profile.d/*.sh, so the standalone Claude installer's
# bindir (~/.local/bin) is invisible to fish unless we add it explicitly.
# fish_add_path is idempotent.
if test -d $HOME/.local/bin
    fish_add_path -gP $HOME/.local/bin
end

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

    # bat ships as `batcat` on Debian/Ubuntu (name clash with bacula). Same
    # pattern as fd; then use it as a nicer cat.
    if command -q batcat; and not command -q bat
        alias bat=batcat
    end
    if functions -q bat; or command -q bat
        alias cat='bat --paging=never'
    end

    # fzf keybindings: Ctrl-R history, Ctrl-T files, Alt-C cd.
    if command -q fzf
        fzf --fish | source
    end
end
