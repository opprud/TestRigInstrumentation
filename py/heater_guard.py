#!/usr/bin/env python3
"""
Safety net: switch the oil heater off when the run is over — however it ends.

Runs detached from any Claude session or dashboard, and talks to the Shelly via
shelly_control.py (MQTT) rather than the API server, so it still works if the
backend is down.

Fires on whichever comes first:
  1. "run_end" appears in the run's telemetry JSONL      (clean finish)
  2. telemetry goes silent past --stale-min              (crashed / killed run)
  3. the absolute --deadline passes                      (overrun backstop)

Turning the heater off is safe in all three cases: the run is finished, dead, or
past its planned end. The failure it guards against is the opposite one — a
crashed run leaving the heater energised overnight.

Usage:
  nohup python3 heater_guard.py --run <run_dir> --deadline <epoch> \
      [--stale-min 15] [--channel heater] >> heater_guard.log 2>&1 &
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SHELLY = os.path.join(HERE, "shelly_control.py")


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def telemetry_file(run_dir: str):
    f = glob.glob(os.path.join(run_dir, "telemetry_*.jsonl"))
    return f[0] if f else None


def saw_run_end(path: str) -> bool:
    try:
        with open(path, errors="replace") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or '"run_end"' not in ln:
                    continue
                try:
                    if json.loads(ln).get("type") == "run_end":
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


def _shelly(args, timeout=60):
    """Run shelly_control.py and return (rc, output)."""
    try:
        p = subprocess.run([sys.executable, SHELLY] + args,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, repr(e)


def heater_state(channel_id: int, channel_name: str):
    """
    True = off, False = on, None = could not determine.

    The API server keeps a persistent MQTT subscription and caches the last
    published state, so it is the reliable source. shelly_control.py --status
    only listens for a few seconds and often prints "???" because the device did
    not publish inside that window — that is UNKNOWN, never "off".
    """
    # Preferred: the API's cached view.
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8000/api/shelly/status", timeout=10) as r:
            data = json.loads(r.read().decode())
        for c in data.get("channels", []):
            if int(c.get("id", -1)) != channel_id:
                continue
            out = c.get("output")
            if not isinstance(out, bool):
                # Absent or null means the API has no fresh state for the channel —
                # that is UNKNOWN. bool(None) would silently read as "off" and let
                # the guard claim VERIFIED without the heater ever being switched.
                log(f"channel {channel_id}: API returned output={out!r} — treating as UNKNOWN")
                return None
            return not out
    except Exception as e:
        log(f"API status unavailable ({e!r}); falling back to MQTT CLI")

    rc, out = _shelly(["--status"])
    if rc != 0:
        return None
    for line in out.splitlines():
        if channel_name.lower() not in line.lower():
            continue
        if "???" in line:
            return None          # device did not publish in the window
        low = line.lower()
        if " off" in low or "false" in low:
            return True
        if " on" in low or "true" in low:
            return False
    return None


def switch_off(channel_id: int, channel_name: str, attempts: int = 12) -> bool:
    """Send the off command until the state can be positively confirmed."""
    unknown = 0
    for i in range(1, attempts + 1):
        rc, out = _shelly(["--off", str(channel_id)])
        log(f"switch-off attempt {i}/{attempts}: rc={rc} {out.strip()[:160]}")
        # The CLI often cannot confirm within its own 5 s window; that is fine,
        # the command is still published. Confirmation comes from the check below.
        st = heater_state(channel_id, channel_name)
        if st is True:
            log(f"VERIFIED: channel {channel_id} ({channel_name}) is OFF")
            return True
        if st is None:
            unknown += 1
            log("state UNKNOWN — command was sent, but could not confirm")
        else:
            log("still reading ON — retrying")
        time.sleep(min(30, 3 * i))
    log(f"!!! could not confirm channel {channel_id} OFF after {attempts} attempts "
        f"({unknown} inconclusive) — COMMAND WAS SENT REPEATEDLY, BUT A HUMAN SHOULD CHECK THE RIG")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="run directory holding telemetry_*.jsonl")
    ap.add_argument("--deadline", type=float, required=True, help="absolute epoch backstop")
    ap.add_argument("--stale-min", type=float, default=15.0,
                    help="minutes of telemetry silence treated as a dead run")
    ap.add_argument("--channel-id", type=int, default=0)
    ap.add_argument("--channel", default="heater")
    ap.add_argument("--poll", type=float, default=60.0)
    a = ap.parse_args()

    log(f"heater guard armed: run={a.run} channel={a.channel_id}/{a.channel} "
        f"deadline={datetime.fromtimestamp(a.deadline).isoformat(timespec='seconds')} "
        f"stale={a.stale_min}min")

    tel = telemetry_file(a.run)
    if tel is None:
        log(f"no telemetry file in {a.run} yet; will keep looking")

    while True:
        now = time.time()

        if tel is None:
            tel = telemetry_file(a.run)

        reason = None
        if tel and saw_run_end(tel):
            reason = "run_end in telemetry (clean finish)"
        elif tel:
            age_min = (now - os.path.getmtime(tel)) / 60.0
            if age_min > a.stale_min:
                reason = f"telemetry silent for {age_min:.1f} min (run appears dead)"
        if reason is None and now >= a.deadline:
            reason = "absolute deadline passed (overrun backstop)"

        if reason:
            log(f"TRIGGER: {reason}")
            ok = switch_off(a.channel_id, a.channel)
            log("heater guard done" if ok else "heater guard exiting WITHOUT confirmation")
            return 0 if ok else 1

        time.sleep(a.poll)


if __name__ == "__main__":
    sys.exit(main())
