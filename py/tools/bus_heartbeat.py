#!/usr/bin/env python3
"""Stamp this agent's liveness onto its dedicated heartbeat branch (ticket 0009).

Call this on a cadence AS PART OF THE AGENT'S POLL CYCLE -- so the heartbeat tracks
the agent actually polling the bus, not merely the machine being powered on. If the
agent stops polling, the heartbeat stops, and the OTHER agent's watchdog notices.

    python3 py/tools/bus_heartbeat.py --agent windows

It writes a single-file, PARENTLESS commit to ``bus-hb-<agent>`` and force-pushes it,
so the heartbeat is visible to the other agents without ever adding a commit to moj.
Fast and side-effect-free on the working tree (pure plumbing: hash-object / mktree /
commit-tree / update-ref / push).
"""

from __future__ import annotations

import argparse
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bus_common import git, load_config, repo_root, safe_console, utcnow_iso  # noqa: E402


def write_heartbeat(repo: str, agent: str, cfg: dict) -> tuple[str, str]:
    branch = f"bus-hb-{agent}"
    ts = utcnow_iso()
    # Best-effort: which BUS.md head did we last see? Informational only.
    bus_head = git(["rev-parse", "--short", f"origin/{cfg['branch']}:TEAM/BUS.md"],
                   repo, check=False) or "?"
    content = (
        f"# heartbeat: {agent}\n"
        f"last_seen_utc: {ts}\n"
        f"cadence_sec: {cfg['heartbeat_cadence_sec']}\n"
        f"host: {socket.gethostname()}\n"
        f"bus_head: {bus_head}\n"
    )
    blob = git(["hash-object", "-w", "--stdin"], repo, stdin=content)
    tree = git(["mktree"], repo, stdin=f"100644 blob {blob}\theartbeat.md\n")
    commit = git(["commit-tree", tree, "-m", f"hb: {agent} {ts}"], repo)  # no -p => parentless
    git(["update-ref", f"refs/heads/{branch}", commit], repo)
    git(["push", "-f", "origin", branch], repo)
    return ts, branch


def main() -> None:
    ap = argparse.ArgumentParser(description="Stamp an agent heartbeat (ticket 0009).")
    ap.add_argument("--agent", required=True, help="this agent's name, e.g. windows or pi")
    a = ap.parse_args()
    safe_console()
    repo = repo_root()
    cfg = load_config(repo)
    if a.agent not in cfg["agents"]:
        print(f"warning: '{a.agent}' not in configured agents {cfg['agents']}", file=sys.stderr)
    ts, branch = write_heartbeat(repo, a.agent, cfg)
    print(f"heartbeat {a.agent} -> {branch} @ {ts}")


if __name__ == "__main__":
    main()
