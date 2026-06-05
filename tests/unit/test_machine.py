"""Unit tests for the host-side helpers in bin/machine. No VM required."""
import argparse
import contextlib
import importlib.util
import io
import os
import socket
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load_machine(extra_env: dict[str, str] | None = None):
    """Import bin/machine fresh with a controlled environment."""
    for key, value in (extra_env or {}).items():
        os.environ[key] = value
    # bin/machine has no .py suffix, so spec_from_file_location can't infer a
    # loader; build one explicitly via SourceFileLoader.
    loader = SourceFileLoader("machine_cli", str(ROOT / "bin" / "machine"))
    spec = importlib.util.spec_from_loader("machine_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def proc(rc: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    """A fake CompletedProcess for mocked run()/lima_shell() calls."""
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


class _MachineTestCase(unittest.TestCase):
    """Loads bin/machine fresh against a temp projects.toml."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        projects = Path(self.tmp.name) / "projects.toml"
        projects.write_text(
            'default_profile = "cypress"\n'
            "[blog]\n"
            'repos = ["git@github.com:me/blog.git"]\n'
            "[wallet]\n"
            'profiles = ["cypress", "supabase-fly"]\n'
            'shell = "fish"\n'
            'repos = ["git@github.com:me/a.git", "git@github.com:me/b.git"]\n'
            "[bare]\n"
            "profiles = []\n"
            'repos = []\n'
        )
        self.m = load_machine({
            "PROJECTS_FILE": str(projects),
            "MACHINE_STATE_DIR": str(Path(self.tmp.name) / "state"),
        })

    def tearDown(self):
        self.tmp.cleanup()


class TestHelpers(_MachineTestCase):
    def test_repo_basename(self):
        self.assertEqual(self.m.repo_basename("git@github.com:me/blog.git"), "blog")
        self.assertEqual(self.m.repo_basename("https://github.com/me/x"), "x")

    def test_validate_name_rejects_bad(self):
        with self.assertRaises(SystemExit):
            self.m.validate_name("Bad_Name")
        self.m.validate_name("ok-name-2")  # no raise

    def test_default_profiles(self):
        self.assertEqual(self.m.default_profiles({}), [])
        self.assertEqual(
            self.m.default_profiles({"default_profile": "cypress"}), ["cypress"])
        self.assertEqual(self.m.default_profiles({"default_profile": ""}), [])

    def test_project_profiles_default_and_explicit(self):
        self.assertEqual(self.m.project_profiles("blog"), ["cypress"])
        self.assertEqual(self.m.project_profiles("wallet"), ["cypress", "supabase-fly"])
        self.assertEqual(self.m.project_profiles("bare"), [])

    def test_project_shell(self):
        self.assertEqual(self.m.project_shell("blog"), "zsh")
        self.assertEqual(self.m.project_shell("wallet"), "fish")

    def test_param_set_args_quotes_values(self):
        args = self.m.param_set_args(
            {"gitName": 'Ivan "K"', "shell": "zsh"})
        self.assertEqual(args[0], "--set")
        self.assertIn('.param.gitName = "Ivan \\"K\\""', args[1])
        self.assertIn('.param.shell = "zsh"', args[3])

    def test_render_template_without_golden(self):
        out = self.m.render_template("wallet", ["cypress", "supabase-fly"], golden=False)
        text = out.read_text()
        self.assertIn("base:", text)
        self.assertNotIn("file://", text)
        # Lima prepends each successively merged base, so profiles are listed
        # reversed and base.yaml last → base.sh executes first.
        entries = [l for l in text.splitlines() if l.startswith("- ")]
        self.assertTrue(entries[0].endswith("templates/supabase-fly.yaml"))
        self.assertTrue(entries[1].endswith("templates/cypress.yaml"))
        self.assertTrue(entries[2].endswith("templates/base.yaml"))

    def test_render_template_with_golden(self):
        img = Path(self.tmp.name) / "base-arm64.img"
        img.write_bytes(b"fake")
        out = self.m.render_template("wallet", [], golden=True, golden_image=img)
        text = out.read_text()
        self.assertIn(f"file://{img}", text)
        # images come before base so the cached disk wins
        self.assertLess(text.index("images:"), text.index("base:"))

    def test_render_template_rejects_unknown_profile(self):
        with self.assertRaises(SystemExit):
            self.m.render_template("wallet", ["nope"], golden=False)

    def test_configure_ssh_agent_uses_1password_socket_when_present(self):
        sock_path = Path(self.tmp.name) / "agent.sock"
        srv = socket.socket(socket.AF_UNIX)
        self.addCleanup(srv.close)
        srv.bind(str(sock_path))
        with mock.patch.dict(os.environ, {
            "ONEPASS_SOCK": str(sock_path),
            "SSH_AUTH_SOCK": "/orig/agent.sock",
        }):
            self.m.configure_ssh_agent()
            self.assertEqual(os.environ["SSH_AUTH_SOCK"], str(sock_path))

    def test_configure_ssh_agent_keeps_default_when_socket_missing(self):
        with mock.patch.dict(os.environ, {
            "ONEPASS_SOCK": str(Path(self.tmp.name) / "nope.sock"),
            "SSH_AUTH_SOCK": "/orig/agent.sock",
        }):
            self.m.configure_ssh_agent()
            self.assertEqual(os.environ["SSH_AUTH_SOCK"], "/orig/agent.sock")

    def test_configure_ssh_agent_ignores_non_socket_path(self):
        not_a_socket = Path(self.tmp.name) / "plain-file"
        not_a_socket.write_text("")
        with mock.patch.dict(os.environ, {
            "ONEPASS_SOCK": str(not_a_socket),
            "SSH_AUTH_SOCK": "/orig/agent.sock",
        }):
            self.m.configure_ssh_agent()
            self.assertEqual(os.environ["SSH_AUTH_SOCK"], "/orig/agent.sock")

    def test_configure_ssh_agent_warns_about_removed_flag(self):
        import io
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {
            "MACHINE_USE_1PASSWORD": "1",
            "ONEPASS_SOCK": str(Path(self.tmp.name) / "nope.sock"),
            "SSH_AUTH_SOCK": "/orig/agent.sock",
        }), mock.patch("sys.stderr", stderr):
            self.m.configure_ssh_agent()
        self.assertIn("MACHINE_USE_1PASSWORD", stderr.getvalue())

    def test_resolve_up_known_project(self):
        urls, profiles = self.m.resolve_up_target(self.m.load_projects(), "blog")
        self.assertEqual(urls, ["git@github.com:me/blog.git"])
        self.assertEqual(profiles, ["cypress"])


class TestZeroConfig(unittest.TestCase):
    """Behavior with no projects.toml at all (zero-config mode)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = load_machine({
            "PROJECTS_FILE": str(Path(self.tmp.name) / "projects.toml"),
            "MACHINE_STATE_DIR": str(Path(self.tmp.name) / "state"),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_projects_missing_file_returns_empty(self):
        self.assertEqual(self.m.load_projects(), {})

    def test_resolve_up_default_never_prompts(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            urls, profiles = self.m.resolve_up_target({}, "default")
        self.assertEqual((urls, profiles), ([], []))

    def test_resolve_up_unknown_name_accepted(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch("builtins.input", return_value="y"):
            urls, profiles = self.m.resolve_up_target({}, "scratch")
        self.assertEqual((urls, profiles), ([], []))

    def test_resolve_up_unknown_name_declined(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch("builtins.input", return_value=""):
            with self.assertRaises(SystemExit):
                self.m.resolve_up_target({}, "scratch")

    def test_resolve_up_unknown_name_eof_aborts(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch("builtins.input", side_effect=EOFError):
            with self.assertRaises(SystemExit):
                self.m.resolve_up_target({}, "scratch")

    def test_resolve_up_existing_vm_skips_prompt(self):
        with mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            urls, profiles = self.m.resolve_up_target({}, "scratch")
        self.assertEqual((urls, profiles), ([], []))

    def test_resolve_up_ad_hoc_honors_default_profile(self):
        urls, profiles = self.m.resolve_up_target(
            {"default_profile": "cypress"}, "default")
        self.assertEqual((urls, profiles), ([], ["cypress"]))

    def test_parser_defaults_project_to_default(self):
        ap = self.m.build_parser()
        for cmd in ("up", "down", "ssh", "claude", "destroy", "secrets"):
            self.assertEqual(ap.parse_args([cmd]).project, "default", cmd)
        self.assertEqual(ap.parse_args(["up", "blog"]).project, "blog")

    def test_parser_run_still_requires_project(self):
        with self.assertRaises(SystemExit):
            self.m.build_parser().parse_args(["run"])


class TestCloneWarnings(_MachineTestCase):
    def test_clone_repo_returns_warning_on_deps_failure(self):
        # 1st lima_shell: repo-present probe (rc 1 = absent)
        # run(): git clone (ok)
        # 2nd lima_shell: deps install (rc 1 = failed)
        with mock.patch.object(self.m, "lima_shell",
                               side_effect=[proc(1), proc(1)]) as sh, \
             mock.patch.object(self.m, "run", return_value=proc(0)):
            warning = self.m.clone_repo("blog", "git@github.com:me/blog.git")
        self.assertEqual(warning, "deps install failed for blog — re-run inside the VM")
        self.assertEqual(sh.call_count, 2)

    def test_clone_repo_returns_none_on_success(self):
        with mock.patch.object(self.m, "lima_shell",
                               side_effect=[proc(1), proc(0)]), \
             mock.patch.object(self.m, "run", return_value=proc(0)):
            self.assertIsNone(self.m.clone_repo("blog", "git@github.com:me/blog.git"))

    def test_clone_repo_returns_none_when_already_present(self):
        with mock.patch.object(self.m, "lima_shell", return_value=proc(0)), \
             mock.patch.object(self.m, "run") as run_mock:
            self.assertIsNone(self.m.clone_repo("blog", "git@github.com:me/blog.git"))
        run_mock.assert_not_called()

    def _run_up(self, clone_result):
        """Drive cmd_up with all I/O mocked; return captured stdout."""
        out = io.StringIO()
        with mock.patch.object(self.m, "close_lima_ssh_master"), \
             mock.patch.object(self.m, "verify_repos_reachable"), \
             mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch.object(self.m, "run", return_value=proc(0)), \
             mock.patch.object(self.m, "clone_repo", return_value=clone_result), \
             contextlib.redirect_stdout(out):
            rc = self.m.cmd_up(argparse.Namespace(project="blog"))
        return rc, out.getvalue()

    def test_cmd_up_prints_check_summary_without_warnings(self):
        rc, out = self._run_up(None)
        self.assertEqual(rc, 0)
        self.assertIn("✓ blog ready", out)
        self.assertNotIn("⚠", out)

    def test_cmd_up_prints_warning_summary_and_exits_zero(self):
        rc, out = self._run_up("deps install failed for blog — re-run inside the VM")
        self.assertEqual(rc, 0)
        self.assertIn("⚠ blog ready with warnings:", out)
        self.assertIn("  deps install failed for blog — re-run inside the VM", out)
        self.assertNotIn("✓", out)

    def test_cmd_up_closes_ssh_master_after_provisioning(self):
        # Provisioning (`limactl start`) may `chsh` the login shell; the SSH
        # master opened during start stays pinned to the old shell, so it must
        # be closed *after* start or `machine ssh` reuses the wrong shell.
        mgr = mock.Mock()
        mgr.run.return_value = proc(0)
        with mock.patch.object(self.m, "close_lima_ssh_master", mgr.close), \
             mock.patch.object(self.m, "verify_repos_reachable"), \
             mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch.object(self.m, "run", mgr.run), \
             mock.patch.object(self.m, "clone_repo", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()):
            self.m.cmd_up(argparse.Namespace(project="blog"))
        names = [c[0] for c in mgr.mock_calls]
        start_idx = next(
            i for i, c in enumerate(mgr.mock_calls)
            if c[0] == "run" and list(c[1][0][:2]) == ["limactl", "start"]
        )
        self.assertIn("close", names[start_idx:])


class TestPrimaryRepoWorkdir(_MachineTestCase):
    def test_returns_guest_printed_path(self):
        with mock.patch.object(
            self.m, "lima_shell",
            return_value=proc(0, stdout="/home/other.linux/code/blog\n"),
        ) as sh:
            self.assertEqual(self.m._primary_repo_workdir("blog"),
                             "/home/other.linux/code/blog")
        guest_cmd = sh.call_args.args[1]
        self.assertIn('cd "$HOME/code/blog" && pwd', guest_cmd[-1])

    def test_returns_none_when_repo_dir_missing(self):
        with mock.patch.object(self.m, "lima_shell", return_value=proc(1)):
            self.assertIsNone(self.m._primary_repo_workdir("blog"))

    def test_does_not_read_host_user_env(self):
        # Regression: used to KeyError on missing USER and to fabricate
        # /home/$USER.linux/... from the host environment.
        with mock.patch.dict(self.m.os.environ, {}, clear=True), \
             mock.patch.object(
                 self.m, "lima_shell",
                 return_value=proc(0, stdout="/home/whoever/code/blog\n"),
             ):
            self.assertEqual(self.m._primary_repo_workdir("blog"),
                             "/home/whoever/code/blog")

    def test_returns_none_for_project_without_repos(self):
        with mock.patch.object(self.m, "lima_shell") as sh:
            self.assertIsNone(self.m._primary_repo_workdir("bare"))
        sh.assert_not_called()


class TestAgentSelfHeal(_MachineTestCase):
    def test_agent_has_keys_true_on_rc0(self):
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(0, stdout="key\n")):
            self.assertTrue(self.m._agent_has_keys())

    def test_agent_has_keys_false_on_rc1(self):
        with mock.patch.object(self.m.subprocess, "run", return_value=proc(1)):
            self.assertFalse(self.m._agent_has_keys())

    def test_agent_has_keys_false_when_probe_times_out(self):
        # A wedged/locked host agent (e.g. a locked 1Password) accepts the
        # socket connection but never answers `ssh-add -l`. Treat the timeout
        # as "no keys" so the heal step no-ops instead of hanging machine ssh.
        with mock.patch.object(
                self.m.subprocess, "run",
                side_effect=self.m.subprocess.TimeoutExpired(
                    cmd="ssh-add", timeout=5)):
            self.assertFalse(self.m._agent_has_keys())

    def test_agent_has_keys_probe_is_time_boxed(self):
        # Guards against reintroducing the indefinite hang: the host probe
        # MUST pass a finite timeout to subprocess.run.
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(0)) as run:
            self.m._agent_has_keys()
        timeout = run.call_args.kwargs.get("timeout")
        self.assertIsNotNone(timeout, "ssh-add -l probe must set a timeout")
        self.assertGreater(timeout, 0)

    def test_heal_noop_when_no_sock(self):
        with mock.patch.object(self.m.Path, "exists", return_value=False), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=True) as keys, \
             mock.patch.object(self.m, "lima_shell") as sh, \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_not_called()
        sh.assert_not_called()
        keys.assert_not_called()

    def test_heal_noop_when_host_agent_empty(self):
        with mock.patch.object(self.m.Path, "exists", return_value=True), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=False), \
             mock.patch.object(self.m, "lima_shell") as sh, \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_not_called()
        sh.assert_not_called()

    def test_heal_noop_when_vm_has_keys(self):
        with mock.patch.object(self.m.Path, "exists", return_value=True), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=True), \
             mock.patch.object(self.m, "lima_shell", return_value=proc(0)), \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_not_called()

    def test_heal_closes_master_when_vm_empty(self):
        with mock.patch.object(self.m.Path, "exists", return_value=True), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=True), \
             mock.patch.object(self.m, "lima_shell", return_value=proc(1)), \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_called_once_with("blog")

    def test_heal_closes_master_when_probe_times_out(self):
        with mock.patch.object(self.m.Path, "exists", return_value=True), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=True), \
             mock.patch.object(
                 self.m, "lima_shell",
                 side_effect=self.m.subprocess.TimeoutExpired(
                     cmd="ssh-add", timeout=5)), \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_called_once_with("blog")


class TestCommandsSelfHeal(_MachineTestCase):
    def test_cmd_ssh_heals_before_exec(self):
        with mock.patch.object(self.m, "_heal_stale_agent_master") as heal, \
             mock.patch.object(self.m, "_primary_repo_workdir", return_value=None), \
             mock.patch.object(self.m.os, "execvp"):
            self.m.cmd_ssh(argparse.Namespace(project="blog"))
        heal.assert_called_once_with("blog")

    def test_cmd_claude_heals_before_exec(self):
        with mock.patch.object(self.m, "_heal_stale_agent_master") as heal, \
             mock.patch.object(self.m, "_primary_repo_workdir", return_value=None), \
             mock.patch.object(self.m.os, "execvp"), \
             contextlib.redirect_stderr(io.StringIO()):
            self.m.cmd_claude(argparse.Namespace(project="blog"))
        heal.assert_called_once_with("blog")


class TestSecretsReachability(_MachineTestCase):
    def _secrets_args(self, **kw):
        defaults = dict(project="blog", repo=None, clear=False)
        defaults.update(kw)
        return argparse.Namespace(**defaults)

    def test_cmd_secrets_dies_when_vm_unreachable(self):
        with mock.patch.object(self.m.shutil, "which", return_value="/usr/bin/op"), \
             mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(255, stderr="ssh: connect failed")), \
             self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.cmd_secrets(self._secrets_args())
        self.assertIn("cannot reach VM 'blog'", err.getvalue())
        self.assertIn("machine up blog", err.getvalue())

    def test_cmd_secrets_keeps_nothing_found_message(self):
        # Probe succeeds but finds no .envrc files (or ~/code doesn't exist
        # yet — the guest script ends in `|| true`): not an error, exit 1
        # with the existing hint.
        with mock.patch.object(self.m.shutil, "which", return_value="/usr/bin/op"), \
             mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(0, stdout="")), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            rc = self.m.cmd_secrets(self._secrets_args())
        self.assertEqual(rc, 1)
        self.assertIn("no repos with 'use op_env'", err.getvalue())

    def test_cmd_secrets_clear_repo_dies_when_vm_unreachable(self):
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(255, stderr="ssh: connect failed")), \
             self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.cmd_secrets_clear(self._secrets_args(repo="blog", clear=True))
        self.assertIn("cannot reach VM 'blog'", err.getvalue())


class TestSyncOneEnv(_MachineTestCase):
    def test_op_failure_returns_false_and_skips_vm(self):
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(1, stderr="not signed in")) as sp, \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            ok = self.m.sync_one_env("blog", "abc123", "blog")
        self.assertFalse(ok)
        self.assertEqual(sp.call_count, 1)  # op only; limactl never invoked
        self.assertIn("not signed in", err.getvalue())

    def test_success_pipes_secret_via_stdin_not_argv(self):
        secret = "TOKEN=hunter2\n"
        with mock.patch.object(self.m.subprocess, "run",
                               side_effect=[proc(0, stdout=secret), proc(0)]) as sp, \
             contextlib.redirect_stdout(io.StringIO()):
            ok = self.m.sync_one_env("blog", "abc123", "blog")
        self.assertTrue(ok)
        push = sp.call_args_list[1]
        self.assertEqual(push.kwargs.get("input"), secret)
        self.assertNotIn(secret, " ".join(push.args[0]))
        self.assertEqual(push.args[0][:3], ["limactl", "shell", "blog"])


if __name__ == "__main__":
    unittest.main()
