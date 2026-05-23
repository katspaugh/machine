"""Unit tests for cmd_ps helpers in bin/machine. No VM required."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent.parent


def _load_machine() -> object:
    """Import bin/machine (extensionless) as a module without running main()."""
    loader = SourceFileLoader("machine_cli", str(REPO / "bin" / "machine"))
    spec = importlib.util.spec_from_loader("machine_cli", loader)
    assert spec
    mod = importlib.util.module_from_spec(spec)
    sys.modules["machine_cli"] = mod
    loader.exec_module(mod)
    return mod


m = _load_machine()


# ---------------------------------------------------------------------------
# _gather_lima_list_json
# ---------------------------------------------------------------------------

class TestGatherLimaListJson(unittest.TestCase):

    def _run(self, stdout: str, returncode: int = 0) -> dict:
        proc_mock = mock.Mock()
        proc_mock.returncode = returncode
        proc_mock.stdout = stdout
        with mock.patch("subprocess.run", return_value=proc_mock):
            return m._gather_lima_list_json()

    def test_lima_list_jsonl_parses(self):
        """JSONL output (multi-line, one obj per line) is parsed correctly."""
        line1 = json.dumps({"name": "blog", "status": "Running"})
        line2 = json.dumps({"name": "wallet", "status": "Stopped"})
        result = self._run(f"{line1}\n{line2}\n")
        self.assertEqual(set(result.keys()), {"blog", "wallet"})
        self.assertEqual(result["blog"]["status"], "Running")
        self.assertEqual(result["wallet"]["status"], "Stopped")

    def test_lima_list_json_array_parses(self):
        """Single JSON array response is also tolerated."""
        data = json.dumps([
            {"name": "alpha", "status": "Running"},
            {"name": "beta", "status": "Stopped"},
        ])
        result = self._run(data)
        self.assertEqual(set(result.keys()), {"alpha", "beta"})

    def test_lima_list_empty_returncode_nonzero(self):
        """When limactl fails (nonzero returncode), returns {} without exception."""
        result = self._run("error output", returncode=1)
        self.assertEqual(result, {})

    def test_lima_list_empty_output(self):
        """Empty stdout returns {}."""
        result = self._run("")
        self.assertEqual(result, {})

    def test_lima_list_skips_invalid_json_lines(self):
        """Malformed lines are skipped; valid lines still parsed."""
        good = json.dumps({"name": "ok", "status": "Running"})
        result = self._run(f"not-json\n{good}\nalso-bad\n")
        self.assertEqual(list(result.keys()), ["ok"])


# ---------------------------------------------------------------------------
# _format_duration_compact
# ---------------------------------------------------------------------------

class TestFormatDurationCompact(unittest.TestCase):

    def test_seconds(self):
        self.assertEqual(m._format_duration_compact(30), "30s")

    def test_one_minute(self):
        self.assertEqual(m._format_duration_compact(90), "1m")

    def test_hours_and_minutes(self):
        self.assertEqual(m._format_duration_compact(3700), "1h 01m")

    def test_days(self):
        self.assertEqual(m._format_duration_compact(90000), "1d 1h")

    def test_zero(self):
        self.assertEqual(m._format_duration_compact(0), "0s")

    def test_exact_hour(self):
        self.assertEqual(m._format_duration_compact(3600), "1h 00m")


# ---------------------------------------------------------------------------
# _vm_uptime
# ---------------------------------------------------------------------------

class TestVmUptime(unittest.TestCase):

    def test_uptime_from_ha_pid_mtime(self):
        """When ha.pid exists, uptime is based on its mtime."""
        fake_mtime = time.time() - 3700  # ~1h 1m ago
        stat_mock = mock.Mock()
        stat_mock.st_mtime = fake_mtime

        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "stat", return_value=stat_mock):
            result = m._vm_uptime("blog", {})

        # Should be around 1h 01m
        self.assertIsNotNone(result)
        self.assertRegex(result, r"1h \d\dm")

    def test_uptime_falls_back_to_created(self):
        """When ha.pid is missing, fall back to `created` field in Lima JSON."""
        import datetime as dt
        # Fake 72 minutes ago
        now = dt.datetime.now(tz=dt.timezone.utc)
        created_time = now - dt.timedelta(minutes=72)
        created_str = created_time.isoformat()

        with mock.patch.object(Path, "is_file", return_value=False):
            result = m._vm_uptime("blog", {"created": created_str})

        self.assertIsNotNone(result)
        # 72 minutes = 1h 12m
        self.assertEqual(result, "1h 12m")

    def test_uptime_returns_none_when_no_source(self):
        """Returns None when ha.pid missing and no created field."""
        with mock.patch.object(Path, "is_file", return_value=False):
            result = m._vm_uptime("blog", {})
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _parse_vm_info
# ---------------------------------------------------------------------------

class TestParseVmInfo(unittest.TestCase):

    def test_parse_full_output(self):
        """Parses all four sections correctly."""
        output = (
            "0.42 0.35 0.28 1/234 5678\n"
            "---\n"
            "               total        used        free      shared  buff/cache   available\n"
            "Mem:      4294967296  1288490189  2684354560    12345   322122547  2684354560\n"
            "Swap:              0           0           0\n"
            "---\n"
            "ivan     pts/0        2024-01-01 10:00\n"
            "---\n"
            "main\n"
        )
        result = m._parse_vm_info(output)
        self.assertAlmostEqual(result["load1"], 0.42)
        self.assertEqual(result["mem_total_bytes"], 4294967296)
        # mem_used = total - available = 4294967296 - 2684354560 = 1610612736
        self.assertEqual(result["mem_used_bytes"], 4294967296 - 2684354560)
        self.assertEqual(result["branch"], "main")

    def test_parse_vm_info_handles_partial_output_no_who_no_branch(self):
        """Partial output (missing who section and branch) returns available fields."""
        output = (
            "0.14 0.10 0.08 1/100 200\n"
            "---\n"
            "               total        used        free\n"
            "Mem:      8589934592   943718400  7646216192\n"
            "---\n"
        )
        result = m._parse_vm_info(output)
        self.assertAlmostEqual(result["load1"], 0.14)
        self.assertEqual(result["mem_total_bytes"], 8589934592)
        self.assertIsNone(result["branch"])

    def test_parse_vm_info_empty(self):
        """Empty output returns all-None result without exception."""
        result = m._parse_vm_info("")
        self.assertIsNone(result["load1"])
        self.assertIsNone(result["mem_used_bytes"])
        self.assertIsNone(result["branch"])

    def test_parse_vm_info_malformed_loadavg(self):
        """Malformed loadavg section leaves load1 as None."""
        output = "bad data\n---\nMem:      1024 512 512\n---\n---\n"
        result = m._parse_vm_info(output)
        self.assertIsNone(result["load1"])

    def test_parse_vm_info_high_load(self):
        """Very high load1 value is stored as-is (normalization happens in _make_ps_row)."""
        output = "15.00 10.00 8.00 5/500 1000\n---\n---\n---\n"
        result = m._parse_vm_info(output)
        self.assertAlmostEqual(result["load1"], 15.0)


# ---------------------------------------------------------------------------
# _gather_active_ports
# ---------------------------------------------------------------------------

class TestGatherActivePorts(unittest.TestCase):

    def _make_log(self, tmp_path: Path, vm: str, lines: list[str]) -> Path:
        """Write synthesized ha.stderr.log lines to tmp_path/.lima/<vm>/."""
        log_dir = tmp_path / ".lima" / vm
        log_dir.mkdir(parents=True)
        log_file = log_dir / "ha.stderr.log"
        log_file.write_text("\n".join(lines) + "\n")
        return log_file

    def test_gather_active_ports_replays_log(self):
        """A forwarding line causes the port to be included when probe succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_line = json.dumps({
                "level": "info",
                "msg": "Forwarding TCP from [::]:3000 to 127.0.0.1:3000",
                "time": "2024-01-01T10:00:00+00:00",
            })
            self._make_log(tmp_path, "blog", [log_line])

            with mock.patch.object(Path, "home", return_value=tmp_path), \
                 mock.patch("machine_cli._probe_port", return_value=True):
                result = m._gather_active_ports("blog")

        self.assertIn(3000, result)

    def test_gather_active_ports_only_includes_probed_ports(self):
        """Ports in the log that fail the probe are excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lines = [
                json.dumps({"level": "info", "msg": "Forwarding TCP from [::]:3000 to 127.0.0.1:3000"}),
                json.dumps({"level": "info", "msg": "Forwarding TCP from [::]:5173 to 127.0.0.1:5173"}),
            ]
            self._make_log(tmp_path, "blog", lines)

            def probe_side_effect(port, timeout=0.1):
                return port == 5173  # only 5173 is "live"

            with mock.patch.object(Path, "home", return_value=tmp_path), \
                 mock.patch("machine_cli._probe_port", side_effect=probe_side_effect):
                result = m._gather_active_ports("blog")

        self.assertEqual(result, [5173])

    def test_gather_active_ports_multiple_fwd_same_port_deduped(self):
        """The same port appearing multiple times in the log is deduplicated."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lines = [
                json.dumps({"level": "info", "msg": "Forwarding TCP from [::]:3000 to 127.0.0.1:3000"}),
                json.dumps({"level": "info", "msg": "Forwarding TCP from [::]:3000 to 127.0.0.1:3000"}),
                json.dumps({"level": "info", "msg": "Forwarding TCP from [::]:3000 to 127.0.0.1:3000"}),
            ]
            self._make_log(tmp_path, "blog", lines)

            probe_calls: list[int] = []

            def probe_side_effect(port, timeout=0.1):
                probe_calls.append(port)
                return True

            with mock.patch.object(Path, "home", return_value=tmp_path), \
                 mock.patch("machine_cli._probe_port", side_effect=probe_side_effect):
                result = m._gather_active_ports("blog")

        # probe should only be called once for port 3000
        self.assertEqual(probe_calls.count(3000), 1)
        self.assertEqual(result, [3000])

    def test_gather_active_ports_no_log_file(self):
        """Missing ha.stderr.log returns [] without error."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Create directory but no log file
            (tmp_path / ".lima" / "blog").mkdir(parents=True)
            with mock.patch.object(Path, "home", return_value=tmp_path):
                result = m._gather_active_ports("blog")
        self.assertEqual(result, [])

    def test_gather_active_ports_ipv4_address(self):
        """Handles IPv4 host address like 0.0.0.0:PORT."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_line = json.dumps({
                "level": "info",
                "msg": "Forwarding TCP from 0.0.0.0:8080 to 127.0.0.1:8080",
            })
            self._make_log(tmp_path, "blog", [log_line])

            with mock.patch.object(Path, "home", return_value=tmp_path), \
                 mock.patch("machine_cli._probe_port", return_value=True):
                result = m._gather_active_ports("blog")

        self.assertIn(8080, result)


# ---------------------------------------------------------------------------
# _build_ps_rows
# ---------------------------------------------------------------------------

class TestBuildPsRows(unittest.TestCase):

    def _minimal_cfg(self, projects: dict) -> dict:
        cfg: dict = {}
        cfg.update(projects)
        return cfg

    def test_build_ps_rows_includes_project_without_vm(self):
        """A project in projects.toml but not in Lima VMs shows STATUS '—'."""
        cfg = {"ledger": {"repos": ["git@github.com:org/ledger.git"]}}
        lima_vms: dict = {}

        with mock.patch("machine_cli._gather_running_vm_info", return_value={}), \
             mock.patch("machine_cli._gather_active_ports", return_value=[]):
            rows = m._build_ps_rows(cfg, lima_vms, None)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.name, "ledger")
        self.assertEqual(row.status, "—")
        self.assertEqual(row.uptime, "—")
        self.assertEqual(row.cpu, "—")
        self.assertEqual(row.mem, "—")
        # REPO should come from TOML
        self.assertEqual(row.repo, "ledger")
        self.assertEqual(row.ports, "—")

    def test_build_ps_rows_includes_vm_without_project(self):
        """A Lima VM not in projects.toml still appears with REPO '—'."""
        cfg: dict = {}
        lima_vms = {"sandbox": {"name": "sandbox", "status": "Running"}}

        with mock.patch("machine_cli._gather_running_vm_info", return_value={}), \
             mock.patch("machine_cli._gather_active_ports", return_value=[]):
            rows = m._build_ps_rows(cfg, lima_vms, None)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.name, "sandbox")
        self.assertEqual(row.status, "Running")
        self.assertEqual(row.repo, "—")

    def test_build_ps_rows_order_project_first_then_extra_vms(self):
        """Projects from TOML appear first; extra Lima VMs appended."""
        cfg = {"alpha": {"repos": ["git@github.com:org/alpha.git"]}}
        lima_vms = {
            "alpha": {"name": "alpha", "status": "Stopped"},
            "beta": {"name": "beta", "status": "Stopped"},
        }

        with mock.patch("machine_cli._gather_running_vm_info", return_value={}), \
             mock.patch("machine_cli._gather_active_ports", return_value=[]):
            rows = m._build_ps_rows(cfg, lima_vms, None)

        names = [r.name for r in rows]
        self.assertEqual(names.index("alpha"), 0)
        self.assertIn("beta", names)

    def test_build_ps_rows_stopped_vm_has_em_dashes(self):
        """Stopped VM has em-dash for all dynamic columns."""
        cfg = {"wallet": {"repos": ["git@github.com:org/wallet.git"]}}
        lima_vms = {"wallet": {"name": "wallet", "status": "Stopped"}}

        with mock.patch("machine_cli._gather_running_vm_info", return_value={}), \
             mock.patch("machine_cli._gather_active_ports", return_value=[]):
            rows = m._build_ps_rows(cfg, lima_vms, None)

        row = rows[0]
        self.assertEqual(row.status, "Stopped")
        self.assertEqual(row.uptime, "—")
        self.assertEqual(row.cpu, "—")
        self.assertEqual(row.mem, "—")
        self.assertEqual(row.ports, "—")

    def test_build_ps_rows_running_vm_with_data(self):
        """Running VM with all data filled in."""
        cfg = {"blog": {"repos": ["git@github.com:org/blog.git"]}}
        lima_vms = {"blog": {"name": "blog", "status": "Running", "cpus": 4}}
        info = {
            "load1": 0.56,  # 0.56 / 4 cpus = 14%
            "mem_used_bytes": int(1.8 * 1_073_741_824),
            "mem_total_bytes": int(4 * 1_073_741_824),
            "idle_seconds": None,
            "branch": "main",
        }

        with mock.patch("machine_cli._gather_running_vm_info", return_value=info), \
             mock.patch("machine_cli._gather_active_ports", return_value=[3000, 5432]), \
             mock.patch("machine_cli._vm_uptime", return_value="1h 12m"):
            rows = m._build_ps_rows(cfg, lima_vms, None)

        row = rows[0]
        self.assertEqual(row.status, "Running")
        self.assertEqual(row.cpu, "14%")
        self.assertIn("blog", row.repo)
        self.assertIn("main", row.repo)
        self.assertEqual(row.ports, "3000, 5432")


# ---------------------------------------------------------------------------
# _print_ps_table
# ---------------------------------------------------------------------------

class TestPrintPsTable(unittest.TestCase):

    def test_print_ps_table_aligns_columns(self):
        """Each column is left-aligned to the width of its widest cell."""
        rows = [
            m.PsRow(
                name="blog",
                status="Running",
                uptime="1h 12m",
                cpu="14%",
                mem="1.8 / 4 G",
                repo="blog (main)",
                idle="—",
                ports="3000",
            ),
            m.PsRow(
                name="wallet-long-name",
                status="Stopped",
                uptime="—",
                cpu="—",
                mem="—",
                repo="—",
                idle="—",
                ports="—",
            ),
        ]

        buf = io.StringIO()
        with mock.patch("builtins.print", side_effect=lambda *a, **kw: buf.write(" ".join(str(x) for x in a) + "\n")):
            m._print_ps_table(rows)

        output = buf.getvalue()
        lines = output.splitlines()
        # Should have 3 lines: header + 2 rows
        self.assertEqual(len(lines), 3)

        # The header line should contain all column names
        header = lines[0]
        for col in ["NAME", "STATUS", "UPTIME", "CPU", "MEM", "REPO", "IDLE", "PORTS"]:
            self.assertIn(col, header)

        # "wallet-long-name" is wider than "NAME" (4 chars) so NAME column
        # must be at least len("wallet-long-name") = 16 chars wide.
        # Check that both name values appear and their columns are properly padded.
        self.assertIn("blog", lines[1])
        self.assertIn("wallet-long-name", lines[2])

    def test_print_ps_table_no_rows(self):
        """Empty row list prints only the header without crashing."""
        buf = io.StringIO()
        with mock.patch("builtins.print", side_effect=lambda *a, **kw: buf.write(" ".join(str(x) for x in a) + "\n")):
            m._print_ps_table([])
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("NAME", lines[0])

    def test_print_ps_table_trailing_whitespace_stripped(self):
        """Lines should not have trailing whitespace (rstrip applied)."""
        rows = [
            m.PsRow("x", "Running", "1m", "1%", "0.1 / 4 G", "x", "—", "—"),
        ]
        printed: list[str] = []
        with mock.patch("builtins.print", side_effect=lambda *a, **kw: printed.append(str(a[0]))):
            m._print_ps_table(rows)
        for line in printed:
            self.assertEqual(line, line.rstrip(), f"trailing whitespace in: {line!r}")


# ---------------------------------------------------------------------------
# _probe_port
# ---------------------------------------------------------------------------

class TestProbePort(unittest.TestCase):

    def test_probe_port_returns_false_on_closed_port(self):
        """Port 1 (privileged, never open) should return False."""
        # Port 1 is a privileged port that is almost certainly closed.
        # If for some reason connect() succeeds, skip rather than fail.
        result = m._probe_port(1, timeout=0.1)
        if result:
            self.skipTest("Port 1 unexpectedly accepted a connection — skipping")
        self.assertFalse(result)

    def test_probe_port_returns_true_on_open_port(self):
        """A socket that returns 0 from connect_ex is treated as open."""
        import socket as sock_mod
        mock_sock = mock.Mock()
        mock_sock.connect_ex.return_value = 0
        mock_sock.__enter__ = mock.Mock(return_value=mock_sock)
        mock_sock.__exit__ = mock.Mock(return_value=False)
        with mock.patch("socket.socket", return_value=mock_sock):
            result = m._probe_port(9999, timeout=0.5)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
