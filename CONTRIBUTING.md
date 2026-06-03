# Contributing to machine

## Dev setup

Run from a clone — no Homebrew install of `machine` needed (Lima 2.0+ must be on your PATH: `brew install lima`, or use the Nix flake):

```sh
git clone git@github.com:katspaugh/machine.git
cd machine
bin/machine doctor          # verifies lima, SSH agent, git identity
```

In dev mode `projects.toml` lives at the repo root
(`cp projects.toml.example projects.toml`) and generated state goes to
`.build/`.

## Tests

| Command | Needs | What |
|---|---|---|
| `bash tests/lint.sh` | shellcheck (optional) | Shellcheck + Python parse check |
| `bash tests/unit.sh` | nothing | Host-side unit tests for `bin/machine` |
| `bash tests/run-all.sh <project>` | a provisioned VM | Full in-VM smoke suite |

CI runs lint + unit on every PR. The VM smoke suite runs on pushes to main
and nightly (`.github/workflows/smoke.yml`) — it boots a real Lima VM, so
it's not on the PR path. Please run lint + unit locally before pushing.

`tests/run-all.sh` also reads the target VM from `MACHINE_NAME` if no argument is given.

## Writing a profile (the most useful contribution)

A profile is a pair: `templates/<name>.yaml` + `provision/<name>.sh`.

1. Copy an existing pair, e.g. `templates/playwright.yaml` +
   `provision/playwright.sh`, to your profile's name.
2. The template's `provision:` entry points at your script via the
   `provision/` symlink (Lima v2 forbids `../` in `file:` locators).
3. Scripts run as root by default (`mode: system`); use `mode: user` for
   per-user steps. **They re-run on every boot — keep them idempotent**
   (guard installs with `command -v` checks, use `apt-get install -y`,
   never append blindly to dotfiles).
4. Test it: add the profile to a project in `projects.toml`, then
   `bin/machine destroy <p> && bin/machine up <p>`, and check
   `limactl shell <p> sudo tail -100 /var/log/cloud-init-output.log`.
5. Add a smoke test `tests/smoke-<name>.sh` mirroring an existing one
   (e.g. `tests/smoke-cypress.sh` — target the VM via `$MACHINE_NAME` and
   `limactl shell`), and a row in the README's Provisioning section.

## Pull requests

- One logical change per PR.
- `bash tests/lint.sh && bash tests/unit.sh` green.
- Update `CHANGELOG.md` under `## [Unreleased]` if the change is user-visible.
