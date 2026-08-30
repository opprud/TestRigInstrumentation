"""Shared helpers for the agent-bus hardening tools (ticket 0009).

The agent bus is ``TEAM/BUS.md`` on the ``AutoDetectScope_moj`` branch. It only
works if each agent (windows = architect, pi = tester) reliably polls it. On
2026-08-19 the Pi's poll stopped by mistake and a ticket handoff sat unread until
a human noticed -- the same silent-failure class as the heater guard and the tacho
freeze. These tools add a **heartbeat + an independent watchdog** so a dead poll
fails LOUD, not silent.

Design note -- why heartbeats do NOT land on the working branch:
    Stamping liveness every few minutes onto ``moj`` would bury real history under
    hundreds of commits a day. Instead each agent stamps its heartbeat onto its own
    dedicated branch ``bus-hb-<agent>`` as a single **parentless** commit that is
    force-pushed each time, so that branch never grows and ``moj`` stays clean. The
    watchdog reads the other agents' heartbeats with ``git fetch`` + ``git show``,
    never a checkout.
"""

import json
import os
import subprocess
from datetime import datetime, timezone


def safe_console() -> None:
    """Make stdout/stderr never crash on non-ASCII (the alarm text has emoji).

    A legacy Windows console is cp1252, so ``print("⚠️ …")`` raises
    UnicodeEncodeError. Reconfigure to UTF-8 with replacement so console echo is at
    worst cosmetic; file writes are already explicit UTF-8.
    """
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def utcnow_iso() -> str:
    """Current UTC time as ``2026-08-30T06:20:00Z`` (matches the bus timestamps)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    """Parse the ``...Z`` timestamps we write, returning an aware datetime."""
    return datetime.fromisoformat(s.strip().replace("Z", "+00:00"))


def git(args, cwd, stdin=None, check=True) -> str:
    """Run a git command non-interactively and return its stdout (stripped).

    Uses BYTES I/O deliberately: on Windows ``text=True`` translates ``\\n`` to
    ``\\r\\n`` on the child's stdin, which corrupts newline-delimited plumbing input
    (``mktree`` then reads a path with a trailing ``\\r``). Encoding as UTF-8 bytes
    ourselves keeps every ``\\n`` a ``\\n`` on every platform.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    data = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    p = subprocess.run(
        ["git", *args], cwd=cwd, input=data, capture_output=True, env=env,
    )
    if check and p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError("git " + " ".join(args) + " -> " + (err or "failed"))
    return p.stdout.decode("utf-8", "replace").strip()


def journal(tag: str, priority: str, msg: str) -> None:
    """Best-effort line into the systemd journal (survives a freeze, ticket 0033).

    A no-op wherever ``systemd-cat`` is absent (e.g. Windows), so the shared tools never
    crash on their own reporting path -- which would be the worst possible moment, since
    that path only runs when something already went wrong.
    """
    try:
        subprocess.run(["systemd-cat", "-t", tag, "-p", priority],
                       input=(msg + "\n").encode("utf-8"), check=False)
    except (FileNotFoundError, OSError):
        pass


def repo_root(start=None) -> str:
    """Absolute path to the repo root, found from this file's location."""
    start = start or os.path.dirname(os.path.abspath(__file__))
    return git(["rev-parse", "--show-toplevel"], cwd=start)


def load_config(repo: str) -> dict:
    """Load ``py/bus_config.json`` (cadence, threshold, agents, branch, notify)."""
    with open(os.path.join(repo, "py", "bus_config.json"), encoding="utf-8") as f:
        return json.load(f)
