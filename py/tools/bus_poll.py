#!/usr/bin/env python3
"""Poll the agent bus on a timer, stamp the heartbeat, and shout if BUS.md moved (ticket 0009).

Why this exists on the Pi and not on the architect's side
---------------------------------------------------------
``bus_heartbeat.py`` is documented as "call this from the agent's poll cycle", so the
heartbeat proves the agent is really polling. That works for an agent whose poll is a
continuously running loop. **The Pi agent is an interactive session, and it is legitimately
silent for long stretches** -- it spent 55 minutes at a time doing nothing but waiting during
the 13 h run of 2026-08-29, which is correct behaviour, not a fault.

Tie the heartbeat to that session and a quiet stretch reads as death: with
``stale_threshold_sec`` at 1800 the other side's watchdog would have declared the Pi dark
repeatedly through a night when nothing was wrong. **An alarm that cries wolf gets ignored,
and then the real one is missed** -- which is the exact failure ticket 0009 exists to stop.

So on the Pi the *poll itself* is timer-driven, and this script is that poll. It is not a
wrapper stamping a meaningless liveness bit next to a poll: it genuinely fetches the branch
and reads BUS.md, and only then stamps the heartbeat. What the heartbeat then asserts is
"the Pi's bus polling is alive", which is true, useful, and independent of whether a session
happens to be mid-task.

It also makes the ticket's actual goal -- *a message is never silently unread* -- hold in the
case that matters most: a new BUS.md message during a 13 h unattended run now lands in the
persistent journal within one cadence, instead of waiting for a human to prompt the agent.

    python3 py/tools/bus_poll.py --agent pi
    python3 py/tools/bus_poll.py --agent pi --quiet     # only speak when something changed
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bus_common import git, load_config, repo_root, safe_console, utcnow_iso  # noqa: E402

STATE_FILE = "py/.bus_poll_state.json"


def _state_path(repo: str) -> str:
    return os.path.join(repo, STATE_FILE)


def read_state(repo: str) -> dict:
    try:
        with open(_state_path(repo), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def write_state(repo: str, st: dict) -> None:
    with open(_state_path(repo), "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Timer-driven bus poll + heartbeat (ticket 0009).")
    ap.add_argument("--agent", required=True, help="this agent's name, e.g. pi")
    ap.add_argument("--quiet", action="store_true", help="print only when BUS.md changed")
    a = ap.parse_args()
    safe_console()
    repo = repo_root()
    cfg = load_config(repo)
    branch = cfg["branch"]

    # 1. The poll proper: fetch, then read BUS.md's blob id off the remote ref.
    git(["fetch", "--quiet", "origin", branch], repo, check=False)
    head = git(["rev-parse", "--short", f"origin/{branch}:TEAM/BUS.md"], repo, check=False) or "?"

    st = read_state(repo)
    prev = st.get("bus_head")
    changed = head != "?" and prev is not None and head != prev

    if changed:
        # Loud, and into the persistent journal so it survives a freeze (ticket 0033).
        subj = git(["log", "-1", "--format=%s", f"origin/{branch}", "--", "TEAM/BUS.md"],
                   repo, check=False) or ""
        msg = f"BUS MOVED for {a.agent}: TEAM/BUS.md {prev} -> {head} | {subj[:160]}"
        print(msg, flush=True)
        subprocess.run(["systemd-cat", "-t", "bus-poll", "-p", "warning"],
                       input=msg + "\n", text=True, check=False)
    elif not a.quiet:
        print(f"bus unchanged for {a.agent}: TEAM/BUS.md @ {head}")

    st.update({"bus_head": head, "last_poll_utc": utcnow_iso()})
    write_state(repo, st)

    # 2. Only now stamp the heartbeat -- it asserts that the poll above actually ran.
    hb = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bus_heartbeat.py")
    r = subprocess.run([sys.executable, hb, "--agent", a.agent],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
