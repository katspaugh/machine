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
    """The unprivileged Lima user. SUDO_USER is reliable when invoked via sudo."""
    u = os.environ.get("SUDO_USER")
    if u and u != "root":
        return u
    for p in pwd.getpwall():
        if p.pw_name != "root" and p.pw_shell.endswith(("sh", "zsh", "fish")):
            return p.pw_name
    sys.exit("provision: cannot determine lima user")


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
        argv = (
            ["sudo", "-u", self.user, "-i", "bash", "-lc", cmd]
            if as_user
            else ["bash", "-lc", cmd]
        )
        subprocess.run(argv, env=self.env, check=check)


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
    runner.sh("apt-get update -qq && apt-get -y upgrade")
    runner.sh(
        "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "
        + " ".join(shlex.quote(p) for p in pkgs)
    )


def step_apt_repo(cfg: dict[str, Any], runner: Runner, gate: dict[str, str], codename: str) -> None:
    repos = cfg.get("apt_repo", [])
    if not repos:
        return
    runner.sh(f"install -m 0755 -d {KEYRINGS}")
    for r in repos:
        if not when_ok(r, env=gate):
            continue
        name = r["name"]
        key = f"{KEYRINGS}/{name}.gpg"
        deb = r["deb"].format(codename=codename, arch=gate["arch"])
        pkgs = " ".join(shlex.quote(p) for p in r["packages"])
        # NodeSource hands us ASCII-armored keys; everything else returns binary.
        # `--dearmor` is a no-op on already-binary input in modern gpg, so apply uniformly.
        runner.sh(
            f"curl -fsSL {shlex.quote(r['key_url'])} "
            f"| gpg --batch --yes --dearmor -o {key} && chmod a+r {key}"
        )
        runner.sh(
            f'echo "deb [arch={gate["arch"]} signed-by={key}] {deb}" '
            f"> {SOURCES_D}/{name}.list"
        )
        runner.sh("apt-get update -qq")
        runner.sh(
            f"DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends {pkgs}"
        )
        if "post_shell" in r:
            runner.sh(r["post_shell"])


def step_installer(cfg: dict[str, Any], runner: Runner, sentinels: Sentinels) -> None:
    for i in cfg.get("installer", []):
        name = i["name"]
        tag = f"installer-{name}"
        if sentinels.done(tag):
            print(f"[provision] {tag}: already done", file=sys.stderr)
            continue
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
            continue
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
        return
    runner.sh("corepack enable", as_user=True)
    for p in c.get("prepare", []):
        runner.sh(f"corepack prepare {shlex.quote(p)} --activate", as_user=True)
    sentinels.mark("corepack")


def step_npm_global(cfg: dict[str, Any], runner: Runner) -> None:
    n = cfg.get("npm_global")
    if not n:
        return
    pkgs = " ".join(shlex.quote(p) for p in n.get("packages", []))
    if pkgs:
        runner.sh(f"npm install -g {pkgs}", as_user=True)


def step_profile_d(cfg: dict[str, Any], runner: Runner) -> None:
    for name in (cfg.get("profile_d") or {}).get("files", []):
        runner.sh(f"install -m 0644 {PROFILE_D_SRC / name} {PROFILE_D_DST / name}")


def step_claude(cfg: dict[str, Any], runner: Runner) -> None:
    c = cfg.get("claude")
    if not c:
        return
    marketplace = c["marketplace"]
    marketplace_id = marketplace.rsplit("/", 1)[-1]
    runner.sh(
        f"claude plugin marketplace add {shlex.quote(marketplace)} 2>&1 "
        f"| grep -vi 'already' || true",
        as_user=True,
    )
    for p in c.get("plugins", []):
        runner.sh(
            f"claude plugin install {shlex.quote(f'{p}@{marketplace_id}')} 2>&1 "
            f"| grep -vi 'already installed' || true",
            as_user=True,
        )
    enabled = ",\n    ".join(f'"{p}@{marketplace_id}": true' for p in c.get("plugins", []))
    settings = (
        "{\n"
        f'  "permissions": {{ "defaultMode": "{c.get("default_permission_mode", "auto")}" }},\n'
        f"  \"enabledPlugins\": {{\n    {enabled}\n  }}\n"
        "}\n"
    )
    user_home = runner.env["USER_HOME"]
    user = runner.env["LIMA_USER"]
    quoted = shlex.quote(settings)
    runner.sh(
        f"install -d -m 0755 -o {user} -g {user} {user_home}/.claude && "
        f"printf %s {quoted} | install -m 0644 -o {user} -g {user} /dev/stdin "
        f"{user_home}/.claude/settings.json"
    )


def step_shell(cfg: dict[str, Any], runner: Runner, gate: dict[str, str]) -> None:
    for s in cfg.get("shell", []):
        if not when_ok(s, env=gate):
            continue
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
