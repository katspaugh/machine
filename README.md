# machine — one isolated Lima VM per project

A reproducible Lima VM per GitHub project, with Docker, Node, agent CLIs (Claude Code, Codex), signed git, and Cypress preinstalled. Each project lives in its own VM so they can't see each other and the host filesystem isn't mounted.

Claude Code comes pre-installed with the official marketplace and these plugins enabled: `frontend-design`, `superpowers`, `github`, `typescript-lsp`, `security-guidance`, `commit-commands`, `chrome-devtools-mcp`, `supabase`. Permission `defaultMode` is set to `auto`.

## Prerequisites

```sh
brew install lima
```

- An SSH key on the host, loaded into the macOS Keychain so the default agent serves it:
  ```sh
  ssh-add --apple-use-keychain ~/.ssh/id_ed25519
  ```
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
- Git config is rendered on the host from `files/git/*.tpl`, substituting your name/email and SSH signing pubkey (from `~/.ssh/id_ed25519.pub`), then pushed to the VM.
- GitHub auth + commit signing both use the forwarded macOS SSH agent. Private keys never leave the host; the VM only sees signatures and `ssh -A` proxied auth.

## Threat model

No host filesystem is mounted. Each project gets its own VM, so a compromise of one project can't reach another's code or env. The host exposes one channel: the forwarded SSH agent (auth + signing — private keys stay on the host, the VM can only request signatures while it's running). `.env` files live inside the VM only; if you treat them as secret, keep them out of git.

## Override knobs

| Env var | Default |
|---|---|
| `GIT_NAME` / `GIT_EMAIL` | from host `git config --global` |
| `GIT_SIGNING_PUBKEY_FILE` | `~/.ssh/id_ed25519.pub` |
| `GIT_SIGNING_KEY` | literal pubkey string (overrides the file) |
| `PROJECTS_FILE` | `<repo>/projects.list` |
| `SSH_AUTH_SOCK` | macOS default (the agent your `ssh-add` loaded into) |
