# Nix flake packaging

**Date:** 2026-06-03
**Status:** Approved

## Goal

Let Nix users install and run `machine` straight from the repo:

```sh
nix profile install github:katspaugh/machine
nix run github:katspaugh/machine -- up
```

The flake lives in this repo (no nixpkgs submission for now) and mirrors the
Homebrew formula: install the tree, wrap the entrypoint with a pinned Python,
put Lima on PATH, install shell completions.

## Non-goals

- Submitting to nixpkgs (the derivation is written so it could be lifted
  there later, but that's a separate effort).
- A dev shell or CI flake check.
- NixOS module / home-manager module.
- Adding a `--version` flag to the CLI (the flake version is store-path
  metadata only).

## Design

### 1. `flake.nix`

A single file at the repo root. No flake-utils dependency — a small inline
`forAllSystems` over `aarch64-darwin`, `x86_64-darwin`, `aarch64-linux`,
`x86_64-linux` (Lima supports all four).

- **Inputs:** `nixpkgs` pinned to `nixpkgs-unstable` (its Lima is 2.1.1;
  the 25.05 release branch is too old — machine requires Lima ≥ 2.0 for
  template composition and `mode: data` provisioning).
- **Outputs:**
  - `packages.<system>.machine` (+ `default` alias) — the derivation below.
  - `apps.<system>.default` — runs `bin/machine`, so `nix run` works.

### 2. The derivation

Plain `stdenv.mkDerivation`, a direct translation of `Formula/machine.rb`:

- `pname = "machine"`, `version = "0.2.0"` — a literal string, bumped by
  `scripts/release.sh` (see §3).
- `src = self` — every commit is buildable; users can pin a tag with
  `github:katspaugh/machine/v0.2.0`. Flake sources exclude `.git`, so the
  script's `_IN_CHECKOUT` check is false and it uses XDG config/state dirs,
  exactly as under brew.
- **Build-time guard:** assert `lib.versionAtLeast lima.version "2.0"` so a
  future nixpkgs Lima downgrade fails the build with a clear message instead
  of breaking at runtime.
- **Install phase** (no build phase — `dontBuild = true`):
  - Copy the whole tree to `$out/libexec/machine`.
  - `makeWrapper ${python3}/bin/python3 $out/bin/machine` with
    `--add-flags $out/libexec/machine/bin/machine` and
    `--prefix PATH : ${lima}/bin` — mirrors the formula's shim, and the
    script keeps resolving templates/provision/files relative to `__file__`.
  - Completions via `installShellFiles`:
    `completions/machine.bash` → bash, `completions/_machine` → zsh,
    `completions/machine.fish` → fish.
- **`installCheckPhase`:** run `$out/bin/machine --help` and assert the
  output mentions `machine` and `init` — same smoke test as the formula's
  `test do` block. (`--help` doesn't touch Lima, so it works in the sandbox.)

### 3. `scripts/release.sh`

The formula bump must stay *after* tagging (it pins the tag tarball's
sha256), but the flake version must be in the tagged commit itself, because
`src = self`. So the release flow gains one step before tagging:

1. **New:** `sed` the `version = "X.Y.Z"` line in `flake.nix`, commit
   `Bump flake version to vX.Y.Z` (skipped if already current).
2. Tag + push (existing).
3. Formula sha256 bump, tap mirror, GitHub release (existing).

The preflight "working tree dirty" check still runs first; the new commit is
created by the script itself, so the invariant holds.

### 4. Docs

README Install section gains a Nix subsection after the brew instructions:
`nix profile install github:katspaugh/machine`, `nix run` for one-offs, and
a note that the flake pins its own Lima + Python. Same addition in
`docs/docs/index.html` if it lists install methods.

## Error handling

- nixpkgs Lima drifting below 2.0 → build-time assertion failure with an
  explanatory message.
- Everything else (SSH agent, git config, Lima runtime health) is already
  `machine doctor`'s job and unchanged.

## Testing

No Nix is installed on the dev host, so verification is:

- `nix flake check` / `nix build` + `result/bin/machine --help` on a machine
  with Nix (or via a one-off `nix run` from a pushed branch).
- The derivation's `installCheckPhase` guards regressions for anyone who
  builds it.
- `tests/unit.sh` still passes (release.sh change doesn't touch the CLI).
- Manual: run `scripts/release.sh` flow dry (read-through), since it's only
  exercised at release time.
