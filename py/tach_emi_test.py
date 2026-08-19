#!/usr/bin/env python3
"""
Measure the spurious tach pulse rate — the before/after number for the ferrite fix.

This is the ticket 0003 discriminator, packaged so it is one command at the rig rather
than a sequence someone has to get right while standing there.

What it does: counts accepted tach edges over a window with the drive OFF, then again
with the drive ENERGISED at 0 Hz. The shaft does not rotate in either case, so every
counted edge is spurious. On 2026-08-19, before any ferrites, that was:

    drive off        0.00 Hz
    drive at 0 Hz    9.65 Hz   (= 579 rpm-equivalent, matching the historical +582 offset)

The goal of the ferrite work is to drive the second number to zero.

Requires firmware >= 1.1.1 (TACHDIAG?). Refuses to run if a test is in progress, and
always stops the drive again, including on Ctrl-C.

  python3 tach_emi_test.py [--seconds 60] [--skip-drive]
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_PY = HERE / ".venv/bin/python"


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def tachdiag(port):
    r = subprocess.run([str(VENV_PY), str(HERE / "util_tool.py"),
                        "--port", port, "--json", "tachdiag"],
                       capture_output=True, text=True, timeout=40)
    line = (r.stdout or "").strip().splitlines()
    if not line:
        raise RuntimeError(f"no answer from {port}: {(r.stderr or '').strip()[:120]}")
    return json.loads(line[-1])


def measure(port, seconds, label):
    a = tachdiag(port)
    log(f"{label}: start  accepted={a['accepted']} pulses={a['pulses']} glitches={a['glitches']}")
    time.sleep(seconds)
    b = tachdiag(port)
    d_acc = b["accepted"] - a["accepted"]
    d_gl = b["glitches"] - a["glitches"]
    rate = d_acc / seconds
    log(f"{label}: {d_acc} accepted in {seconds:.0f}s -> {rate:.2f} Hz "
        f"({rate*60:.0f} rpm-equivalent), glitches +{d_gl}")
    return rate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--acm", default="/dev/ttyACM0")
    ap.add_argument("--rs485", default="/dev/ttyUSB0")
    ap.add_argument("--skip-drive", action="store_true",
                    help="only measure with the drive off")
    a = ap.parse_args()

    # Refuse to run during a test — this energises the drive.
    r = subprocess.run(["pgrep", "-f", "python.*acquire_scope_data"],
                       capture_output=True, text=True)
    if [p for p in r.stdout.split() if p.strip()]:
        log("a run is in progress — refusing to energise the drive. Stop the run first.")
        return 1

    fw = subprocess.run([str(VENV_PY), str(HERE / "util_tool.py"),
                         "--port", a.acm, "--json", "info"],
                        capture_output=True, text=True, timeout=40)
    info = json.loads((fw.stdout or "{}").strip().splitlines()[-1])
    log(f"firmware: {info.get('fw')}")
    if str(info.get("fw", "")) < "1.1.1":
        log("TACHDIAG? needs firmware >= 1.1.1 — flash it first")
        return 1

    log("=== A) drive OFF, shaft stationary ===")
    off = measure(a.acm, a.seconds, "  drive off")

    if a.skip_drive:
        log(f"\nRESULT  drive off {off:.2f} Hz  (drive test skipped)")
        return 0

    from rs510_vfd_control import RS510VFDController
    v = RS510VFDController(port=a.rs485, slave_id=3, baudrate=9600, timeout=2.0, debug=False)
    if not v.connect():
        log(f"could not open {a.rs485} — is the API server holding it? "
            f"Result so far: drive off {off:.2f} Hz")
        return 1
    try:
        log("=== B) drive ENERGISED at 0 Hz (shaft does not turn) ===")
        v.set_frequency(0.0)
        v.start_forward(0.0)
        time.sleep(3)
        st = v.get_status()
        log(f"  drive: run={st.run_command} hz_out={st.frequency_out_hz} "
            f"current={st.output_current_a}A")
        on = measure(a.acm, a.seconds, "  drive on ")
        log("")
        log(f"RESULT  drive off {off:.2f} Hz   ->   drive at 0 Hz {on:.2f} Hz")
        log(f"        baseline before any ferrites was 0.00 -> 9.65 Hz")
        if on <= 0.05:
            log("        spurious source GONE — the fix worked")
        elif on < 9.0:
            log(f"        reduced but not gone ({(1-on/9.65)*100:.0f}% down from 9.65 Hz)")
        else:
            log("        unchanged — the pickup path is still open")
    finally:
        try:
            v.stop()
            time.sleep(1)
            st = v.get_status()
            log(f"  drive stopped: run={st.run_command} running={st.is_running}")
        except Exception as e:
            log(f"  !!! COULD NOT STOP THE DRIVE: {e!r} — check the rig")
        v.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
