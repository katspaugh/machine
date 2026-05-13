# machine — one isolated Lima VM per project

A reproducible Lima VM per GitHub project, with Docker, Node, agent CLIs (Claude Code, Codex), GitHub CLI (`gh`), Supabase CLI, fly.io CLI (`flyctl`), signed git, and Cypress preinstalled. Each project lives in its own VM so they can't see each other and the host filesystem isn't mounted.

Claude Code comes pre-installed with the official marketplace and these plugins enabled: `frontend-design`, `superpowers`, `github`, `typescript-lsp`, `security-guidance`, `commit-commands`, `chrome-devtools-mcp`, `supabase`. Permission `defaultMode` is set to `auto`.

## Prerequisites

```sh
brew install lima
```

- An SSH key on the host, served by an agent the VM can forward. Either:
  - **macOS Keychain** (default): `ssh-add --apple-use-keychain ~/.ssh/id_ed25519`
  - **1Password**: enable 1Password → Settings → Developer → *Use the SSH agent*, then run `machine` with `MACHINE_USE_1PASSWORD=1` (see [SSH agent](#ssh-agent) below).
- That key registered as a **signing key** on GitHub (Settings → SSH and GPG keys → New SSH key → Key type: Signing).
- Host `git config --global user.name` and `user.email` set (or override via `GIT_NAME` / `GIT_EMAIL`).

## Setup

```sh
git clone git@github.com:katspaugh/machine.git ~/Sites/machine
cd ~/Sites/machine
cp projects.list.example projects.list
$EDITOR projects.list      # add: <name> = <git-url>
```

Example `projects.list`:

```
blog       = git@github.com:you/blog.git
playground = git@github.com:you/playground.git
```

## Quickstart

```sh
bin/machine up blog        # creates + starts + provisions VM "blog", clones the repo
bin/machine ssh blog       # interactive shell, cwd = ~/code/blog
```

Inside the VM, the repo is at `~/code/<repo-basename>/`. JS deps are installed automatically on first clone (yarn / pnpm / npm, picked from `packageManager` in `package.json`). For env vars, drop a `.env` file in the project — Node's `dotenv` (or your framework) reads it directly. No host-side secrets plumbing.

Host browser → VM web app: ports `3000-3010`, `4200`, `5173-5180`, `8080-8099` are forwarded to `127.0.0.1`.

## Commands

| Command | What |
|---|---|
| `bin/machine list` | List projects from `projects.list` |
| `bin/machine up <p>` | Create if needed, start, provision, clone the repo. Idempotent. |
| `bin/machine down <p>` | Stop the VM |
| `bin/machine ssh <p>` | Interactive shell (cwd = `~/code/<repo>`) |
| `bin/machine run <p> <cmd>...` | Non-interactive command in the VM |
| `bin/machine status <p>` | `limactl list` for the VM |
| `bin/machine update <p>` | Refresh in-place: `apt upgrade`, mise/npm globals, claude installer |
| `bin/machine rebuild <p>` | **Destroys** the VM and rebuilds from scratch (reproducibility test) |
| `bin/machine destroy <p>` | Delete the VM |

## Verifying

```sh
MACHINE_NAME=<project> bash tests/run-all.sh
# or:
bash tests/run-all.sh <project>
```

Runs lint plus smoke tests: boot, agents-on-PATH, docker, node, signed git, port forward, cypress.

## How it works

- `lima.yaml` is the per-VM template. `bin/machine up <p>` runs `limactl create --name=<p> lima.yaml` if the VM doesn't exist, then `limactl start <p>`, then pushes the provision scripts (`provision/[0-9]*.sh`) and runs them as root inside the VM. Re-running `up` is safe: each script has a sentinel and exits early if already done.
- Git config is rendered on the host from `files/git/*.tpl`, substituting your name/email and SSH signing pubkey (from the host's `git config --global user.signingkey`), then pushed to the VM.
- GitHub auth + commit signing both use the forwarded macOS SSH agent. Private keys never leave the host; the VM only sees signatures and `ssh -A` proxied auth.

## SSH agent

By default the VM forwards whatever the host's `SSH_AUTH_SOCK` points at — on macOS that's launchd's agent, which serves keys you loaded with `ssh-add --apple-use-keychain` (passphrase cached in Keychain).

To use 1Password's agent instead — keys never touch `~/.ssh`, every signature prompts for Touch ID:

```sh
brew install 1password-cli                    # only needed for OP_SIGNING_KEY_REF
# In 1Password: Settings → Developer → "Use the SSH agent"
export MACHINE_USE_1PASSWORD=1                # for the current shell, or your shell rc
bin/machine up <project>
```

For the git signing pubkey, the resolution order is:

1. `GIT_SIGNING_KEY=<literal pubkey string>`
2. `OP_SIGNING_KEY_REF=op://Vault/Item/public_key` — fetched via `op read` (requires `op` CLI; triggers Touch ID once at `up` time)
3. `GIT_SIGNING_PUBKEY_FILE=<path>`
4. Host `git config --global user.signingkey` — literal pubkey or path to a `.pub` file (default; whatever you sign host commits with)

## Threat model

No host filesystem is mounted. Each project gets its own VM, so a compromise of one project can't reach another's code or env. The host exposes one channel: the forwarded SSH agent (auth + signing — private keys stay on the host, the VM can only request signatures while it's running). `.env` files live inside the VM only; if you treat them as secret, keep them out of git.

## Override knobs

| Env var | Default |
|---|---|
| `GIT_NAME` / `GIT_EMAIL` | from host `git config --global` |
| `GIT_SIGNING_PUBKEY_FILE` | path to a `.pub` file (overrides host `user.signingkey`) |
| `GIT_SIGNING_KEY` | literal pubkey string (overrides everything) |
| `OP_SIGNING_KEY_REF` | 1Password secret reference for the signing pubkey (e.g. `op://Personal/SSH/public key`) |
| `MACHINE_USE_1PASSWORD` | set `=1` to forward 1Password's SSH agent instead of macOS Keychain |
| `ONEPASS_SOCK` | `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock` |
| `PROJECTS_FILE` | `<repo>/projects.list` |
