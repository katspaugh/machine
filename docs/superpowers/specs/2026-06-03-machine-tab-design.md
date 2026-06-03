# `machine tab` — open a new Terminal tab on the same machine

**Date:** 2026-06-03
**Status:** Approved

## Problem

When working in a tab connected to a machine (`machine ssh foo` or
`machine claude foo`), opening a second shell on the same VM means
manually opening a tab and retyping the command. We want: press a
hotkey → a new Terminal.app tab opens, already connected to the same
machine as the current tab.

## Decisions

- **Per-tab detection** via the process table — not a "last sshed"
  state file, not tab titles, not env vars. The `limactl shell
  <project>` process attached to the current tab's tty is the source
  of truth; it cannot go stale or be clobbered (vim/tmux/user renames
  break title-based detection; env vars add nothing over argv).
- **Hotkey via Shortcuts.app** — built into macOS, no extra
  dependency. We ship the subcommand + docs; the Shortcut is a
  one-action "Run Shell Script".
- **Terminal.app only.** iTerm2 etc. can come later if asked.

## CLI surface

New subcommand:

```
machine tab [project]
```

- With an explicit `project`: skip detection, open a new tab running
  `machine ssh <project>`.
- Without: detect the machine from the frontmost Terminal tab, then
  open the new tab.

## Detection

1. Ask Terminal.app for the current tab's tty:
   `osascript -e 'tell application "Terminal" to get tty of selected tab of front window'`
   → e.g. `/dev/ttys003`.
2. List commands on that tty: `ps -t ttys003 -o args=`.
3. Parse the first line whose argv starts `limactl shell` (matching
   the basename of argv[0], since `ps` may report a full path like
   `/opt/homebrew/bin/limactl`): skip flags
   (`--workdir <dir>`), the first positional argument is the project.
   This covers both forms in use:
   - `limactl shell --workdir /home/... <name>` (`machine ssh`)
   - `limactl shell --workdir /home/... <name> bash -lic ...`
     (`machine claude`)

The argv parser is a small pure function so it is unit-testable
without macOS.

## Opening the tab

A single `osascript` invocation:

1. `activate` Terminal.
2. Via System Events, keystroke ⌘T (Terminal.app's AppleScript
   dictionary has no "make new tab"; a new `do script` window would
   violate the tab requirement).
3. `do script "<machine> ssh <project>" in selected tab of front
   window`, where `<machine>` is the absolute path of the running
   script (`sys.argv[0]` resolved) so it works under brew and dev
   clones regardless of the new login shell's PATH. The project name
   is shell-quoted.

## Errors

All failures `die()` with a specific message:

- Not running on macOS (`sys.platform != "darwin"`).
- `osascript` fails (Terminal not running / not scriptable).
- No `limactl shell` process on the tty: "no machine session in this
  tab — run `machine ssh <project>` first, or pass a project:
  `machine tab <project>`".

## Permissions (docs only)

The first run triggers macOS Automation prompts for whatever invokes
the command (Shortcuts.app, or Terminal itself when run by hand) to
control **Terminal** and **System Events**. One-time; the README
notes it.

## Hotkey setup (docs)

README section: create a Shortcut with a single **Run Shell Script**
action — `/opt/homebrew/bin/machine tab` — and assign a keyboard
shortcut (e.g. ⌃⌘T) in the Shortcut's details pane. Notes: Shortcuts
hotkeys are global (pick a combination that doesn't collide), and the
one-time permission prompts above.

## Testing

- Unit tests (tests/unit/test_machine.py pattern — mocked
  `subprocess.run`):
  - argv parser: `machine ssh` form, `machine claude` form,
    `--workdir` flag handling, no-match → `None`.
  - `cmd_tab`: explicit project skips detection; detection path issues
    the right `osascript`/`ps` calls; each error path dies with the
    expected message.
- The AppleScript/GUI end is verified manually (no host GUI
  automation harness exists in this repo).

## Out of scope

- iTerm2 / other terminals.
- Titling tabs with the project name (nice future UX, separate
  concern).
- State files mapping ttys to projects.
