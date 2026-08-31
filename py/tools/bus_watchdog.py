#!/usr/bin/env python3
"""Independent bus watchdog (ticket 0009): watch the OTHER agents' heartbeats and
fail LOUD if one goes dark.

Run this from an EXTERNAL scheduler (Windows Task Scheduler / cron / systemd timer),
NOT from inside the agent's poll loop -- so it survives the agent stopping and can
report that the agent stopped:

    python3 py/tools/bus_watchdog.py --agent windows        # windows watches pi
    python3 py/tools/bus_watchdog.py --agent pi             # pi watches windows

For each other agent it fetches ``bus-hb-<other>`` and checks how old its
``last_seen_utc`` is:
  * always -> a line in ``py/bus_watchdog.log`` (git-ignored via ``*.log``).
  * on fresh -> stale  -> a LOUD line appended to ``TEAM/BUS.md`` (pushed) naming the
    dark agent, plus an optional external notify command (config ``telegram_cmd``).
  * on stale -> fresh  -> a recovery line.
A standing outage is announced ONCE (state kept in ``py/.bus_watchdog_state.json``,
git-ignored), never every tick.

``--dry-run`` reports what it would do without any git write or notify -- used by the
acceptance test.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bus_common import git, journal, load_config, parse_iso, repo_root, safe_console, utcnow_iso  # noqa: E402

STATE_FILE = "py/.bus_watchdog_state.json"
LOG_FILE = "py/bus_watchdog.log"


def log(repo: str, msg: str) -> None:
    line = f"{utcnow_iso()} {msg}"
    print(line)
    try:
        with open(os.path.join(repo, LOG_FILE), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_state(repo: str) -> dict:
    try:
        with open(os.path.join(repo, STATE_FILE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(repo: str, state: dict) -> None:
    with open(os.path.join(repo, STATE_FILE), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def heartbeat_age(repo: str, other: str) -> tuple:
    """(age_seconds, last_iso) for another agent, or (None, None) if never seen."""
    branch = f"bus-hb-{other}"
    git(["fetch", "-q", "origin", branch], repo, check=False)
    content = git(["show", f"origin/{branch}:heartbeat.md"], repo, check=False)
    if not content:
        return None, None
    ts = None
    for line in content.splitlines():
        if line.startswith("last_seen_utc:"):
            ts = line.split(":", 1)[1].strip()
    if not ts:
        return None, None
    age = (datetime.now(timezone.utc) - parse_iso(ts)).total_seconds()
    return age, ts


def notify(cfg: dict, msg: str) -> None:
    cmd = cfg.get("telegram_cmd")
    if not cmd:
        return
    try:
        subprocess.run(cmd.replace("{msg}", msg), shell=True, timeout=20)
    except Exception:  # notify is best-effort; never let it break the watchdog
        pass


def announce(repo: str, cfg: dict, me: str, text: str, commit_msg: str, dry: bool) -> None:
    if dry:
        print("  [dry-run] would append to BUS.md + push:\n    " + text.strip().replace("\n", "\n    "))
        return
    git(["pull", "--rebase", "-q", "origin", cfg["branch"]], repo, check=False)
    with open(os.path.join(repo, "TEAM", "BUS.md"), "a", encoding="utf-8") as f:
        f.write(text)
    git(["add", "TEAM/BUS.md"], repo)
    git(["commit", "-q", "-m", commit_msg], repo, check=False)
    # Push HEAD explicitly at the remote branch, NOT the bare branch name: an agent may work
    # on a differently-named local branch that merely tracks it (the Pi is on `bus35`). Pushing
    # the bare name picks up whatever stale local branch happens to share it -- on the Pi that
    # is a months-old `AutoDetectScope_moj`, and the push is rejected non-fast-forward.
    git(["push", "-q", "origin", f"HEAD:{cfg['branch']}"], repo, check=False)
    # And never swallow it. A watchdog that cannot announce has itself gone dark, which is the
    # exact failure this ticket exists to prevent -- so say so, loudly, in the log, on stderr,
    # and (on Linux) in the persistent journal.
    if git(["rev-list", "--count", f"origin/{cfg['branch']}..HEAD"], repo, check=False) not in ("0", ""):
        msg = ("WATCHDOG COULD NOT PUSH ITS OWN ALARM -- the alarm is committed locally but has "
               f"NOT reached origin/{cfg['branch']}. The bus does not know. Push by hand.")
        log(repo, msg)
        print(msg, file=sys.stderr, flush=True)
        journal("bus-watchdog", "err", msg)


def check(repo: str, cfg: dict, me: str, dry: bool) -> int:
    others = [x for x in cfg["agents"] if x != me]
    # Only agents expected to be always-on are alarmed on when stale. The architect (windows)
    # is an interactive session that goes legitimately quiet for long stretches, so alarming on
    # it cries wolf (proven 2026-08-30: pi's watchdog posted "windows dark" after a 36-min gap
    # while nothing was wrong). Best-effort agents are still read and logged for visibility, just
    # never turned into a bus alarm. Default = all agents, so this is backward-compatible.
    always_on = cfg.get("always_on", cfg["agents"])
    threshold = cfg["stale_threshold_sec"]
    state = load_state(repo)
    alarms = 0
    for other in others:
        age, ts = heartbeat_age(repo, other)
        watched = other in always_on
        if age is None:
            log(repo, f"{other}: unknown (no heartbeat branch yet) -- not alarming")
            continue
        status = "fresh" if age <= threshold else "stale"
        tag = "" if watched else " [best-effort, not alarmed]"
        log(repo, f"{other}: {status} age={int(age)}s (threshold {threshold}s){tag} last={ts}")
        if not watched:
            state[other] = status
            continue
        prev = state.get(other, "init")
        if status == "stale" and prev != "stale":
            mins = int(age // 60)
            text = (
                f"\n## {utcnow_iso()}  {me} -> ALL\n"
                f"**⚠️ BUS WATCHDOG: `{other}` has gone dark.** Last heartbeat {ts} "
                f"(~{mins} min ago, threshold {threshold // 60} min). Its bus poll may be dead, "
                f"so a message could be sitting unread -- check the {other} agent.\n\n"
                f"-- {me} (watchdog)\n"
            )
            announce(repo, cfg, me, text, f"bus-watchdog: {other} went dark (seen by {me})", dry)
            notify(cfg, f"BUS WATCHDOG: {other} dark since {ts}") if not dry else None
            alarms += 1
        elif status == "fresh" and prev == "stale":
            text = (
                f"\n## {utcnow_iso()}  {me} -> ALL\n"
                f"**✅ BUS WATCHDOG: `{other}` is back.** Heartbeat fresh again ({ts}).\n\n"
                f"-- {me} (watchdog)\n"
            )
            announce(repo, cfg, me, text, f"bus-watchdog: {other} recovered (seen by {me})", dry)
        state[other] = status
    if not dry:
        save_state(repo, state)
    return alarms


def main() -> None:
    ap = argparse.ArgumentParser(description="Independent bus watchdog (ticket 0009).")
    ap.add_argument("--agent", required=True, help="the agent RUNNING the watchdog (it watches the others)")
    ap.add_argument("--dry-run", action="store_true", help="report only; no git write, no notify, no state change")
    a = ap.parse_args()
    safe_console()
    repo = repo_root()
    cfg = load_config(repo)
    n = check(repo, cfg, a.agent, a.dry_run)
    sys.exit(1 if n else 0)


if __name__ == "__main__":
    main()
