# Changelog

All notable changes to `machine` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/). Release notes are generated from this file
by `scripts/release.sh`.

## [Unreleased]

### Removed
- `machine tab` (the macOS new-tab helper). It drove Terminal.app via
  AppleScript and did not work reliably.

## [0.2.3] — 2026-06-05

### Fixed
- `machine ssh` lands in the project's configured login shell again. The SSH
  ControlMaster opened during `machine up` provisioning stayed pinned to the
  pre-`chsh` shell (the golden image bakes zsh before `base.sh` sets the
  project's shell), so sessions reused the wrong shell. `machine up` now
  closes the master after provisioning.
- Provisioned zsh config adds `~/.local/bin` and `~/bin` to `PATH`. zsh does
  not read `~/.profile`, where bash/sh get those entries, so tools installed
  there (e.g. `claude`) were not found under `default_shell = "zsh"`.

## [0.2.2] — 2026-06-04

### Added
- `modern` opt-in profile: bat, delta, fzf, lazygit, helix — opt in per
  project; `rg` remains in the base VM.
- CI smoke workflow: boots a real Lima VM (qemu/KVM on a Linux runner) on
  push to `main` and nightly; runs the full in-VM smoke suite.

### Fixed
- `machine down` is idempotent when the VM is already stopped.

## [0.2.1] — 2026-06-03

### Added
- `machine claude` runs inside a tmux session in the VM — detach with
  `ctrl-b d`, re-run to reattach.
- Nix flake: `nix profile install github:katspaugh/machine`.
- Zero-config default VM: bare `machine up` launches a base VM named
  `default`; unknown names offer an ad-hoc base VM.

### Changed
- SSH agent is auto-detected (1Password socket if present, else
  `SSH_AUTH_SOCK`); `MACHINE_USE_1PASSWORD` is gone.

### Fixed
- `machine up` no longer prints `✓ ready` when a best-effort JS dependency
  install failed — it now ends with `⚠ <name> ready with warnings:` (exit
  code stays 0), so a broken `npm install` is no longer reported as success.
- Guest workdir resolution asks the VM for its real path instead of
  fabricating `/home/$USER.linux/…` from the host environment — fixes a
  crash when `$USER` is unset and wrong paths when host and guest usernames
  differ.
- `machine secrets` now fails with a clear "cannot reach VM" hint when
  `limactl` can't reach the VM, instead of the misleading "nothing found".

## [0.2.0] — 2026-06-02

### Added
- `playwright` profile: OS deps for Playwright's browsers.
- Supabase CLI installed from its `.deb` release artifact.

### Changed
- Rewritten on Lima-native template composition (`base:` stacks) — replaces
  the custom TOML provisioning DSL with Lima templates.
- New projects no longer default to the `cypress` profile.

### Removed
- The Tauri GUI, its Homebrew cask, and the DMG release workflow — `machine`
  is now CLI-only.

[Unreleased]: https://github.com/katspaugh/machine/compare/v0.2.3...HEAD
[0.2.3]: https://github.com/katspaugh/machine/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/katspaugh/machine/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/katspaugh/machine/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/katspaugh/machine/compare/v0.1.6...v0.2.0
