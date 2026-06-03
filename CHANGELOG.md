# Changelog

All notable changes to `machine` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/). Release notes are generated from this file
by `scripts/release.sh`.

## [Unreleased]

### Added
- `modern` opt-in profile: bat, delta, fzf, lazygit, helix (rg stays in base).
- macOS CI smoke workflow: boots a real Lima VM on every push to main and
  nightly, runs the full in-VM smoke suite.

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
- Deps-install warnings, guest workdir resolution, and secrets reachability.

## [0.2.0] — 2026-06-02

### Added
- `playwright` profile: OS deps for Playwright's browsers.
- Supabase CLI installed from its `.deb` release artifact.

[Unreleased]: https://github.com/katspaugh/machine/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/katspaugh/machine/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/katspaugh/machine/compare/v0.1.6...v0.2.0
