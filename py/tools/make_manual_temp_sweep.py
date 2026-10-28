#!/usr/bin/env python3
"""Write a short, manually-driven temperature-sweep profile (VFD run by hand, RS485 unplugged).

    python3 tools/make_manual_temp_sweep.py            # 40-55-70-85-100 C, 10 min each, ~53 min
    python3 tools/make_manual_temp_sweep.py --temps 40 60 80 100

Each temperature level runs the same 10 x 1 min staircase as Keratech22_coarse_FFT_4h40
(600-1200-1800-2400-3000-2400-1800-1200-600-0 rpm). A lead-in at 0 rpm lets the oil reach the
first set-point and gives a stationary reference; a rest minute at SV 25 ends the run.

The profile carries NO `scope_channels`, NO `scope_fft` and NO `acq_points`, so the run leaves
the scope's front-panel channel, timebase, FFT and memory-depth settings exactly as they are.
`control.manual_drive` makes test_runner print the Hz to set instead of writing the drive.
"""
import argparse
import json
from pathlib import Path

STAIR = [600, 1200, 1800, 2400, 3000, 2400, 1800, 1200, 600, 0]


def build(temps, lead_min, step_sec, name):
    rpm, temp = [], []
    t = 0
    rpm.append({"time_sec": 0, "value": 0})
    temp.append({"time_sec": 0, "value": temps[0]})
    t = int(lead_min * 60)
    for T in temps:
        if T != temps[0]:
            temp.append({"time_sec": t, "value": T})
        for v in STAIR:
            rpm.append({"time_sec": t, "value": v})
            t += step_sec
    rpm.append({"time_sec": t, "value": 0})
    temp.append({"time_sec": t, "value": 25})
    t += 60
    minutes = t / 60.0
    return {
        "name": name,
        "description": (
            f"Manual-drive temperature sweep {temps[0]}-{temps[-1]} C, {len(temps)} levels, "
            f"{minutes:.0f} min. VFD operated by hand with RS485 unplugged from it; the runner prints "
            "the Hz to set. Scope settings are NOT touched (no scope_channels / scope_fft / acq_points): "
            "whatever is on the front panel is what is recorded. Heater must be switched on by hand."),
        "duration_minutes": round(minutes, 2),
        "bearing": {"d_mm": 25, "D_mm": 52, "dpw_mm": 38.5},
        "oil": {"viscosity_at_40C_cSt": 22, "viscosity_at_100C_cSt": 0},
        "control": {"rpm_per_hz_guess": 59.5, "open_loop": True, "manual_drive": True,
                    "vfd_max_hz": 50.0},
        "setpoints": {"rpm": rpm, "temperature": temp},
        "acquisition": {"scope_points": "MAX", "samples_per_step": 3, "interval_sec": 12,
                        "waveform_format": "WORD"},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--temps", type=float, nargs="+", default=[40, 55, 70, 85, 100])
    ap.add_argument("--lead-min", type=float, default=2.0)
    ap.add_argument("--name", default="Manual temp sweep 40-100")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] /
                                         "react/public/config/Manual_TempSweep_53min.json"))
    a = ap.parse_args()
    prof = build([int(x) if x == int(x) else x for x in a.temps], a.lead_min, 60, a.name)
    Path(a.out).write_text(json.dumps(prof, indent=1) + "\n")
    print(f"wrote {a.out}  ({prof['duration_minutes']} min)")


if __name__ == "__main__":
    main()
