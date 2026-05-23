#!/usr/bin/env python3
"""
Provisioning dispatcher. Reads /opt/dev-vm/provision.toml plus any number of
profile TOML files (passed as argv), merges them, and applies sections in a
fixed step order. Idempotent via sentinels under /var/lib/dev-vm/provisioned/.

Usage (inside the VM):
  sudo python3 /opt/dev-vm/provision/run.py /opt/dev-vm/provision.toml \\
                                            /opt/dev-vm/profiles/cypress.toml ...

Flags:
  --dry-run    print commands without executing
"""
from __future__ import annotations

import contextlib
import json
import os
import pwd
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

SENTINEL_DIR = Path("/var/lib/dev-vm/provisioned")
KEYRINGS = Path("/etc/apt/keyrings")
SOURCES_D = Path("/etc/apt/sources.list.d")
PROFILE_D_SRC = Path("/opt/dev-vm/files/profile.d")
PROFILE_D_DST = Path("/etc/profile.d")


# --- Host info --------------------------------------------------------------
def detect_user() -> str:
    """The unprivileged Lima user. SUDO_USER is set by sudo and is the only
    source we trust — scanning /etc/passwd would silently pick the wrong user
    on any image with more than one account."""
    u = os.environ.get("SUDO_USER")
    if u and u != "root":
        return u
    sys.exit(
        "provision: SUDO_USER unset or root — run via `sudo python3 run.py ...` "
        "as a non-root user (bin/machine does this for you)."
    )


def detect_arch() -> str:
    return subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()


def detect_codename() -> str:
    out = subprocess.check_output(
        ["bash", "-lc", ". /etc/os-release && echo $VERSION_CODENAME"], text=True
    )
    return out.strip()


# --- Config loading + merging ----------------------------------------------
def load_configs(paths: list[Path]) -> dict[str, Any]:
    """Merge base + profile TOMLs. Lists concatenate; dicts merge (list-typed
    fields inside concat, scalars: first writer wins)."""
    merged: dict[str, Any] = {}
    for path in paths:
        cfg = tomllib.loads(path.read_text())
        for key, value in cfg.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = merged[key] + value
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(merged[key].get(k), list) and isinstance(v, list):
                        merged[key][k] = merged[key][k] + v
                    else:
                        merged[key].setdefault(k, v)
    return merged


def when_ok(item: dict[str, Any], *, env: dict[str, str]) -> bool:
    """`when` is a structured table of key=value gates; all must match."""
    cond = item.get("when") or {}
    return all(env.get(k) == v for k, v in cond.items())


# --- Sentinels --------------------------------------------------------------
class Sentinels:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        if not dry_run:
            SENTINEL_DIR.mkdir(parents=True, exist_ok=True)

    def done(self, tag: str) -> bool:
        return (SENTINEL_DIR / tag).exists()

    def mark(self, tag: str) -> None:
        if self.dry_run:
            return
        (SENTINEL_DIR / tag).touch()


# --- Shell runner ----------------------------------------------------------
class Runner:
    def __init__(self, *, user: str, env: dict[str, str], dry_run: bool):
        self.user = user
        self.env = env
        self.dry_run = dry_run

    def sh(self, cmd: str, *, as_user: bool = False, check: bool = True) -> None:
        prefix = f"  (as {self.user}) " if as_user else "  "
        print(prefix + "$ " + cmd.strip().replace("\n", " \\n "), file=sys.stderr)
        if self.dry_run:
            return
        # -H sets HOME to the target user's home but does NOT invoke the
        # target's login shell. We then run `bash -lc` explicitly. This avoids
        # fish (or any non-bash login shell) trying to parse the bash-syntax
        # command string when sudo's -i flag would route through it.
        argv = (
            ["sudo", "-u", self.user, "-H", "bash", "-lc", cmd]
            if as_user
            else ["bash", "-lc", cmd]
        )
        subprocess.run(argv, env=self.env, check=check)


# --- Step protocol ----------------------------------------------------------
@contextlib.contextmanager
def step(name: str):
    """Context manager that emits machine-readable [step:start] / [step:end] markers."""
    print(f"[step:start] {name}", file=sys.stderr, flush=True)
    try:
        yield
    except subprocess.CalledProcessError as e:
        print(f"[step:end] {name} fail {e.returncode}", file=sys.stderr, flush=True)
        raise
    except BaseException:
        print(f"[step:end] {name} fail 1", file=sys.stderr, flush=True)
        raise
    else:
        print(f"[step:end] {name} ok", file=sys.stderr, flush=True)


# --- Section handlers ------------------------------------------------------
def _blocks(value: Any) -> list[dict[str, Any]]:
    """Normalize a config field that may be a single table or array of tables."""
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    sys.exit(f"provision: expected table or array of tables, got {type(value).__name__}")


def step_apt(cfg: dict[str, Any], runner: Runner, gate: dict[str, str]) -> None:
    """Combine all `[apt]` and `[[apt]]` package lists (filtered by `when`) and install once."""
    pkgs: list[str] = []
    for b in _blocks(cfg.get("apt")):
        if when_ok(b, env=gate):
            pkgs.extend(b.get("packages", []))
    if not pkgs:
        return
    with step("apt update"):
        runner.sh("apt-get update -qq && apt-get -y upgrade")
    first_pkg = pkgs[0]
    step_name = f"apt install {first_pkg}..."
    with step(step_name):
        runner.sh(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "
            + " ".join(shlex.quote(p) for p in pkgs)
        )


def step_apt_repo(cfg: dict[str, Any], runner: Runner, gate: dict[str, str], codename: str) -> None:
    # Fetch all keys + write all source lists in parallel, then run a single
    # apt-get update + install for the union of packages. Previously this
    # serialized N curl-key/apt-update/apt-install cycles; the batched form
    # saves the per-repo apt-update cost (the slow part).
    repos = [r for r in cfg.get("apt_repo", []) if when_ok(r, env=gate)]
    if not repos:
        return
    with step("apt repos"):
        runner.sh(f"install -m 0755 -d {KEYRINGS}")

        parallel = []
        for r in repos:
            name = r["name"]
            key = f"{KEYRINGS}/{name}.gpg"
            deb = r["deb"].format(codename=codename, arch=gate["arch"])
            # NodeSource hands us ASCII-armored keys; everything else returns binary.
            # `--dearmor` is a no-op on already-binary input in modern gpg.
            parallel.append(
                f"( curl -fsSL {shlex.quote(r['key_url'])} "
                f"| gpg --batch --yes --dearmor -o {key} && chmod a+r {key} && "
                f'echo "deb [arch={gate["arch"]} signed-by={key}] {deb}" '
                f"> {SOURCES_D}/{name}.list )"
            )
        # Background each pipeline, wait for all, fail if any failed.
        runner.sh(
            "set -e; " + " & ".join(parallel) + " & "
            "fail=0; for p in $(jobs -p); do wait $p || fail=1; done; "
            "[ $fail -eq 0 ]"
        )

        all_pkgs = " ".join(shlex.quote(p) for r in repos for p in r.get("packages", []))
        if all_pkgs:
            runner.sh("apt-get update -qq")
            runner.sh(
                f"DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends {all_pkgs}"
            )
        for r in repos:
            if "post_shell" in r:
                runner.sh(r["post_shell"])


def step_installer(cfg: dict[str, Any], runner: Runner, sentinels: Sentinels) -> None:
    for i in cfg.get("installer", []):
        name = i["name"]
        tag = f"installer-{name}"
        if sentinels.done(tag):
            print(f"[provision] {tag}: already done", file=sys.stderr)
            print(f"[step:start] install {name}", file=sys.stderr, flush=True)
            print(f"[step:end] install {name} skip already done", file=sys.stderr, flush=True)
            continue
        with step(f"install {name}"):
            env_pre = " ".join(f"{k}={shlex.quote(v)}" for k, v in i.get("env", {}).items())
            cmd = f"curl -fsSL {shlex.quote(i['url'])} | {env_pre} bash".rstrip()
            runner.sh(cmd, as_user=bool(i.get("run_as_user")))
            if "verify" in i:
                runner.sh(i["verify"], as_user=bool(i.get("run_as_user")))
            sentinels.mark(tag)


def step_release(cfg: dict[str, Any], runner: Runner, sentinels: Sentinels, arch: str) -> None:
    for r in cfg.get("release", []):
        name = r["name"]
        tag = f"release-{name}"
        if sentinels.done(tag):
            print(f"[provision] {tag}: already done", file=sys.stderr)
            print(f"[step:start] release {name}", file=sys.stderr, flush=True)
            print(f"[step:end] release {name} skip already done", file=sys.stderr, flush=True)
            continue
        with step(f"release {name}"):
            url = r["url"].format(arch=arch)
            runner.sh(
                f"tmp=$(mktemp -d) && "
                f"curl -fsSL {shlex.quote(url)} | tar -xz -C \"$tmp\" && "
                f"install -m 0755 \"$tmp/{r['bin']}\" {shlex.quote(r['install_to'])} && "
                f"rm -rf \"$tmp\""
            )
            if "verify" in r:
                runner.sh(r["verify"])
            sentinels.mark(tag)


def step_corepack(cfg: dict[str, Any], runner: Runner, sentinels: Sentinels) -> None:
    c = cfg.get("corepack")
    if not c:
        return
    if sentinels.done("corepack"):
        print("[provision] corepack: already done", file=sys.stderr)
        print("[step:start] corepack", file=sys.stderr, flush=True)
        print("[step:end] corepack skip already done", file=sys.stderr, flush=True)
        return
    with step("corepack"):
        # `corepack enable` and `prepare --activate` write shims into the Node
        # install dir (/usr/bin for apt-installed Node), so they need root.
        runner.sh("corepack enable")
        for p in c.get("prepare", []):
            runner.sh(f"corepack prepare {shlex.quote(p)} --activate")
        sentinels.mark("corepack")


def step_npm_global(cfg: dict[str, Any], runner: Runner) -> None:
    n = cfg.get("npm_global")
    if not n:
        return
    pkgs = " ".join(shlex.quote(p) for p in n.get("packages", []))
    # apt-installed Node lives in /usr/lib/node_modules (root-owned), so global
    # installs need root. Single Node per VM = shared globals is fine.
    if pkgs:
        with step("npm globals"):
            runner.sh(f"npm install -g {pkgs}")


def step_profile_d(cfg: dict[str, Any], runner: Runner) -> None:
    files = (cfg.get("profile_d") or {}).get("files", [])
    if not files:
        return
    with step("profile.d"):
        for name in files:
            runner.sh(f"install -m 0644 {PROFILE_D_SRC / name} {PROFILE_D_DST / name}")


def step_claude(cfg: dict[str, Any], runner: Runner) -> None:
    c = cfg.get("claude")
    if not c:
        return
    marketplace = c["marketplace"]
    marketplace_id = marketplace.rsplit("/", 1)[-1]
    # marketplace add / plugin install are noisy when already done: capture
    # output, treat "already" as success, re-raise anything else.
    with step("claude marketplace"):
        runner.sh(_idempotent_claude_cmd(f"plugin marketplace add {shlex.quote(marketplace)}"), as_user=True)
    for p in c.get("plugins", []):
        with step(f"claude plugin {p}"):
            spec = shlex.quote(f"{p}@{marketplace_id}")
            runner.sh(_idempotent_claude_cmd(f"plugin install {spec}"), as_user=True)

    plugins = c.get("plugins", [])
    settings = {
        "permissions": {"defaultMode": c.get("default_permission_mode", "auto")},
        "enabledPlugins": {f"{p}@{marketplace_id}": True for p in plugins},
    }
    settings_json = json.dumps(settings, indent=2) + "\n"
    user_home = runner.env["USER_HOME"]
    user = runner.env["LIMA_USER"]
    quoted = shlex.quote(settings_json)
    with step("claude settings"):
        runner.sh(
            f"install -d -m 0755 -o {user} -g {user} {user_home}/.claude && "
            f"printf %s {quoted} | install -m 0644 -o {user} -g {user} /dev/stdin "
            f"{user_home}/.claude/settings.json"
        )


def _idempotent_claude_cmd(args: str) -> str:
    """Run `claude <args>` and treat 'already installed/exists' output as success.
    Any other non-zero exit is propagated."""
    return (
        f"out=$(claude {args} 2>&1); rc=$?; "
        'if [ $rc -eq 0 ]; then printf "%s\\n" "$out"; '
        'elif printf "%s" "$out" | grep -qi -e "already" -e "exists"; '
        'then printf "%s\\n" "$out"; '
        'else printf "%s\\n" "$out" >&2; exit $rc; fi'
    )


def step_shell(cfg: dict[str, Any], runner: Runner, gate: dict[str, str]) -> None:
    for s in cfg.get("shell", []):
        if not when_ok(s, env=gate):
            continue
        cmd_name = s["cmd"].strip().replace("\n", " ")[:30]
        with step(f"shell {cmd_name}"):
            runner.sh(s["cmd"], as_user=bool(s.get("run_as_user")))


# --- Entry point -----------------------------------------------------------
def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    if not args:
        sys.exit("usage: run.py [--dry-run] <provision.toml> [<profile.toml>...]")

    paths = [Path(a) for a in args]
    for p in paths:
        if not p.exists():
            sys.exit(f"provision: config not found: {p}")

    cfg = load_configs(paths)
    user = detect_user()
    if dry_run:
        # Dry-run is run on the host (macOS) where the lima user doesn't exist.
        # Skip the passwd lookup and synthesize a home dir.
        try:
            home = pwd.getpwnam(user).pw_dir
        except KeyError:
            home = f"/home/{user}.linux"
    else:
        home = pwd.getpwnam(user).pw_dir
    arch = detect_arch() if not dry_run else os.environ.get("DRY_ARCH", "arm64")
    codename = detect_codename() if not dry_run else os.environ.get("DRY_CODENAME", "noble")
    gate = {"arch": arch, "codename": codename}
    env = {**os.environ, "LIMA_USER": user, "USER_HOME": home}

    runner = Runner(user=user, env=env, dry_run=dry_run)
    sentinels = Sentinels(dry_run=dry_run)

    print(
        f"[provision] user={user} home={home} arch={arch} codename={codename} "
        f"dry_run={dry_run} configs={[str(p) for p in paths]}",
        file=sys.stderr,
    )

    # Step order: dependencies flow top to bottom.
    steps = [
        ("apt",        lambda: step_apt(cfg, runner, gate)),
        ("apt_repo",   lambda: step_apt_repo(cfg, runner, gate, codename)),
        ("installer",  lambda: step_installer(cfg, runner, sentinels)),
        ("release",    lambda: step_release(cfg, runner, sentinels, arch)),
        ("corepack",   lambda: step_corepack(cfg, runner, sentinels)),
        ("npm_global", lambda: step_npm_global(cfg, runner)),
        ("profile_d",  lambda: step_profile_d(cfg, runner)),
        ("claude",     lambda: step_claude(cfg, runner)),
        ("shell",      lambda: step_shell(cfg, runner, gate)),
    ]
    for name, fn in steps:
        print(f"[provision] {name}", file=sys.stderr)
        fn()

    print("[provision] done", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
