"""
Renderer module for machine CLI: drives a step-list UI on a TTY or falls back
to plain line-per-step output. Tees all events to a per-run log file.

Parses [step:start] / [step:end] markers from a subprocess's combined stdout+stderr.
"""
from __future__ import annotations

import dataclasses
import datetime
import io
import re
import subprocess
import time
from pathlib import Path
from typing import IO, Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Status = Literal["ok", "skip", "fail"]

# ---------------------------------------------------------------------------
# Protocol regexes (compiled once)
# ---------------------------------------------------------------------------

_START = re.compile(r"^\[step:start\] (?P<name>.+)$")
_END = re.compile(r"^\[step:end\] (?P<name>.+) (?P<status>ok|skip|fail)(?: (?P<detail>.*))?$")

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

ANSI_CLEAR_LINE = "\033[2K"
ANSI_CR = "\r"

# ---------------------------------------------------------------------------
# Spinner / glyphs
# ---------------------------------------------------------------------------

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_STATUS_GLYPH: dict[Status, str] = {
    "ok": "✓",
    "skip": "↷",
    "fail": "✗",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds) // 60
    s = seconds - m * 60
    return f"{m}m {s:.0f}s"


def _glyph_for_status(status: Status) -> str:
    return _STATUS_GLYPH[status]


def _spinner_frame(elapsed: float) -> str:
    idx = int(elapsed * 8) % len(SPINNER_FRAMES)
    return SPINNER_FRAMES[idx]


def _indent(depth: int) -> str:
    return "  " * depth


# ---------------------------------------------------------------------------
# StepHandle
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class StepHandle:
    name: str
    depth: int
    started_at: float           # monotonic seconds
    raw_buffer: list[str]       # lines (without trailing newline)
    _log_seq: int               # ordering tag for log file writes


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class Renderer:
    def __init__(
        self,
        stream: IO[str],
        *,
        tty: bool,
        verbose: bool = False,
        log_path: Path | None = None,
        now: callable = time.monotonic,
        wall_now: callable = lambda: datetime.datetime.now(tz=datetime.timezone.utc),
    ) -> None:
        self._stream = stream
        self._tty = tty
        self._verbose = verbose
        self._log_path = log_path
        self._now = now
        self._wall_now = wall_now

        # Stack of active step handles (outermost first)
        self._stack: list[StepHandle] = []

        # Counter for log sequence numbers
        self._log_seq = 0

        # Whether we have printed the spinner line (only relevant in TTY mode)
        # Tracks how many lines below the "frozen" top steps are currently drawn
        self._active_line_drawn = False

        # Open log file
        self._log_file: IO[str] | None = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_file = open(log_path, "a", encoding="utf-8")

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def step_start(self, name: str, depth: int = 0) -> StepHandle:
        handle = StepHandle(
            name=name,
            depth=depth,
            started_at=self._now(),
            raw_buffer=[],
            _log_seq=self._log_seq,
        )
        self._log_seq += 1

        self._log_record("start", f"{name} depth={depth}")

        if self._tty:
            # If there's an active spinner line, we need to finalize it (freeze it)
            # before drawing the new child step below it.
            if self._active_line_drawn:
                # Finalize the current active line (leave it as-is with frozen spinner)
                # by writing a newline so the cursor is on the next line
                self._stream.write("\n")
                self._active_line_drawn = False

            # Draw the new step's spinner line immediately
            self._draw_step_line(handle)
            self._active_line_drawn = True
        # In plain mode: nothing printed on step_start

        self._stack.append(handle)
        return handle

    def step_end(self, handle: StepHandle, status: Status, detail: str = "") -> None:
        elapsed = self._now() - handle.started_at
        glyph = _glyph_for_status(status)
        indent = _indent(handle.depth)
        duration_str = _format_duration(elapsed)

        self._log_record("end", f"{handle.name} status={status} detail={detail!r} duration={elapsed:.3f}s")

        # Remove from stack
        if handle in self._stack:
            self._stack.remove(handle)

        if self._tty:
            self._tty_finalize_step(handle, status, detail, glyph, indent, duration_str)
        else:
            self._plain_finalize_step(handle, status, detail, glyph, indent, duration_str)

    def raw(self, line: str) -> None:
        """Record one raw output line attributed to the currently active step."""
        # Buffer into the active step
        if self._stack:
            self._stack[-1].raw_buffer.append(line)

        self._log_record("raw", line)

        if self._tty:
            self._tty_raw(line)
        else:
            self._plain_raw(line)

    def consume(self, proc: subprocess.Popen, *, depth: int = 1) -> int:
        """Read proc.stdout line by line. Dispatch [step:start]/[step:end] markers
        to step_start/end. Send everything else to raw(). Return proc.wait()."""
        # Per-consume stack: maps name -> handle for steps started in this consume call
        open_handles: list[StepHandle] = []

        try:
            for raw_line in proc.stdout:
                if isinstance(raw_line, bytes):
                    raw_line = raw_line.decode("utf-8", errors="replace")
                line = raw_line.rstrip("\n").rstrip("\r")

                m = _START.match(line)
                if m:
                    name = m.group("name")
                    h = self.step_start(name, depth=depth)
                    open_handles.append(h)
                    continue

                m = _END.match(line)
                if m:
                    name = m.group("name")
                    status: Status = m.group("status")  # type: ignore[assignment]
                    detail = m.group("detail") or ""

                    # Find the most recent matching handle
                    matched: StepHandle | None = None
                    for h in reversed(open_handles):
                        if h.name == name:
                            matched = h
                            break

                    if matched is None:
                        # Name mismatch — warn and close the most recent open handle
                        if open_handles:
                            innocent = open_handles[-1]
                            self.raw(
                                f"[warn] [step:end] name mismatch: got {name!r}, expected {innocent.name!r}"
                            )
                            open_handles.remove(innocent)
                            self.step_end(
                                innocent,
                                "fail",
                                f"name mismatch (expected {innocent.name!r}, got {name!r})",
                            )
                        else:
                            # No open handle at all — just warn
                            self.raw(f"[warn] [step:end] {name!r} with no matching start")
                        continue

                    open_handles.remove(matched)
                    self.step_end(matched, status, detail)
                    continue

                self.raw(line)
        finally:
            # Close any leftover open steps with fail/unterminated (runs even on exception)
            while open_handles:
                h = open_handles.pop()
                self.step_end(h, "fail", "unterminated")

        return proc.wait()

    def close(self) -> None:
        """Flush + close the log file. Idempotent. Safe to call from __exit__."""
        if self._log_file is not None:
            try:
                self._log_file.flush()
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    def __enter__(self) -> "Renderer":
        return self

    def __exit__(self, *a) -> None:
        self.close()

    # -----------------------------------------------------------------------
    # TTY mode internals
    # -----------------------------------------------------------------------

    def _draw_step_line(self, handle: StepHandle) -> None:
        """Draw (or redraw) the active spinner line for handle. Does NOT write a newline."""
        elapsed = self._now() - handle.started_at
        frame = _spinner_frame(elapsed)
        indent = _indent(handle.depth)
        line = f"{indent}{frame} {handle.name}"
        self._stream.write(f"{ANSI_CR}{ANSI_CLEAR_LINE}{line}")
        self._stream.flush()

    def _tty_finalize_step(
        self,
        handle: StepHandle,
        status: Status,
        detail: str,
        glyph: str,
        indent: str,
        duration_str: str,
    ) -> None:
        # Build the final line
        final = f"{indent}{glyph} {handle.name} ({duration_str})"
        if status == "skip" and detail:
            final += f" — {detail}"
        elif status == "fail" and detail:
            final += f" — {detail}"

        # Overwrite the spinner line (or just finalize it)
        self._stream.write(f"{ANSI_CR}{ANSI_CLEAR_LINE}{final}\n")
        self._active_line_drawn = False

        # On fail: dump buffered raw lines below
        if status == "fail" and handle.raw_buffer:
            raw_indent = indent + "  · "
            for raw_line in handle.raw_buffer:
                self._stream.write(f"{raw_indent}{raw_line}\n")

        # If there is still a parent step in the stack, redraw its spinner
        # (the parent's line was frozen; we now continue with it as active)
        if self._stack:
            parent = self._stack[-1]
            self._draw_step_line(parent)
            self._active_line_drawn = True

        self._stream.flush()

    def _tty_raw(self, line: str) -> None:
        """Handle a raw line in TTY mode."""
        if not self._verbose:
            return

        # Verbose mode: insert the raw line above the spinner
        if self._stack:
            active = self._stack[-1]
            indent = _indent(active.depth + 1)
            prefix = f"{indent}· "
        else:
            prefix = "  · "

        if self._active_line_drawn:
            # Move to start of spinner line, clear it
            self._stream.write(f"{ANSI_CR}{ANSI_CLEAR_LINE}")
            # Print the raw line
            self._stream.write(f"{prefix}{line}\n")
            # Reprint the spinner line
            self._draw_step_line(self._stack[-1])
        else:
            self._stream.write(f"{prefix}{line}\n")

        self._stream.flush()

    # -----------------------------------------------------------------------
    # Plain mode internals
    # -----------------------------------------------------------------------

    def _plain_finalize_step(
        self,
        handle: StepHandle,
        status: Status,
        detail: str,
        glyph: str,
        indent: str,
        duration_str: str,
    ) -> None:
        wall = self._wall_now()
        ts = wall.strftime("%H:%M:%S")
        line = f"[{ts}] {glyph} {indent}{handle.name} ({duration_str})"
        if status == "skip" and detail:
            line += f" — {detail}"
        elif status == "fail" and detail:
            line += f" — {detail}"
        self._stream.write(line + "\n")

        # On fail: dump buffered raw lines below
        if status == "fail" and handle.raw_buffer:
            raw_indent = indent + "  · "
            for raw_line in handle.raw_buffer:
                self._stream.write(f"{raw_indent}{raw_line}\n")

        self._stream.flush()

    def _plain_raw(self, line: str) -> None:
        """Handle a raw line in plain mode."""
        if not self._verbose:
            return

        if self._stack:
            active = self._stack[-1]
            indent = _indent(active.depth + 1)
            prefix = f"{indent}· "
        else:
            prefix = "  · "

        self._stream.write(f"{prefix}{line}\n")
        self._stream.flush()

    # -----------------------------------------------------------------------
    # Log file
    # -----------------------------------------------------------------------

    def _log_record(self, kind: str, payload: str) -> None:
        if self._log_file is None:
            return
        wall = self._wall_now()
        ts = wall.strftime("%Y-%m-%dT%H:%M:%S.") + f"{wall.microsecond // 1000:03d}Z"
        self._log_file.write(f"{ts} {kind} {payload}\n")
        self._log_file.flush()
