#!/usr/bin/env python3
"""Noise-floor analysis for ticket 0035 (motor-decoupled run).

Per scope channel and per OE mic, group every sweep by (condition, temperature, speed) and
report RMS plus band energies, then subtract motor-off from motor-on to isolate the motor's
own contribution.

Condition comes from the *commanded* drive frequency, not from rpm_meas: with the coupling
off, the tach's mark sits on the rig side, so rpm_meas reads 0 even while the motor turns.
Temperature comes from the logged omron_pv_c, never from the profile's target -- decoupled
there is no friction heat and PV can fall short of SV.

Usage:  python3 tools/noise_floor_analysis.py <run.h5> [--json out.json]
"""
import argparse, json, math, sys
from collections import defaultdict

import h5py
import numpy as np

BANDS = [("10-200Hz", 10, 200), ("0.2-5kHz", 200, 5e3),
         ("5-50kHz", 5e3, 50e3), (">50kHz", 50e3, None)]
RPM_PER_HZ = 59.83          # tach calibration; intercept -11.7 is negligible here
TEMP_BIN = 5.0              # C -- PV is quantised to 1 C and drifts, so bin it


def band_energies(v, fs):
    """RMS overall plus per-band RMS, from one Hann-windowed FFT."""
    n = len(v)
    V = np.abs(np.fft.rfft(v * np.hanning(n)))
    fr = np.fft.rfftfreq(n, 1.0 / fs)
    out = {"rms": float(np.std(v)), "vpp": float(np.max(v) - np.min(v))}
    for name, lo, hi in BANDS:
        m = (fr >= lo) & ((fr < hi) if hi else np.ones_like(fr, dtype=bool))
        out[name] = float(np.sqrt(np.sum(V[m] ** 2)) / n)
    return out


def cell_of(attrs):
    """(condition, temperature bin, commanded rpm) for one sweep."""
    hz = float(attrs.get("telem_vfd_cmd_hz", 0.0) or 0.0)
    pv = attrs.get("telem_omron_pv_c")
    pv = float(pv) if pv is not None else float("nan")
    rpm = round(hz * RPM_PER_HZ / 100.0) * 100
    cond = "motor_on" if hz > 0.05 else "motor_off"
    tbin = round(pv / TEMP_BIN) * TEMP_BIN if math.isfinite(pv) else None
    return cond, tbin, (rpm if cond == "motor_on" else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("h5")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    f = h5py.File(a.h5, "r")
    cells = defaultdict(lambda: defaultdict(list))
    pv_seen = defaultdict(list)

    for name in sorted(f["sweeps"]):
        g = f["sweeps"][name]
        cond, tbin, rpm = cell_of(g.attrs)
        if tbin is None:
            continue
        key = (cond, tbin, rpm)
        pv_seen[key].append(float(g.attrs.get("telem_omron_pv_c", np.nan)))
        for ch in g:
            if "voltage" not in g[ch]:
                continue
            d = g[ch]["voltage"]
            fs = float(g[ch].attrs.get("sample_rate", 0)) or 1.0 / float(
                g[ch].attrs.get("x_increment", 4e-7))
            cells[key][ch].append(band_energies(np.asarray(d[:], dtype=float), fs))

    # OE mic captures, keyed the same way off their telem_ stamps
    if "oe_samples" in f:
        for name in sorted(f["oe_samples"]):
            g = f["oe_samples"][name]
            cond, tbin, rpm = cell_of(g.attrs)
            if tbin is None:
                continue
            for ch in g:
                v = np.asarray(g[ch][:], dtype=float)
                fs = float(g[ch].attrs.get("sample_rate_hz", 80000))
                cells[(cond, tbin, rpm)]["oe_" + ch].append(band_energies(v, fs))

    summary = {}
    for key, chans in sorted(cells.items()):
        cond, tbin, rpm = key
        row = {"n_sweeps": max(len(v) for v in chans.values()),
               "pv_mean": float(np.nanmean(pv_seen[key])) if pv_seen[key] else None,
               "channels": {}}
        for ch, lst in chans.items():
            row["channels"][ch] = {k: float(np.mean([x[k] for x in lst])) for k in lst[0]}
        summary[f"{cond}|{tbin:.0f}C|{rpm}rpm"] = row

    # motor-on minus motor-off, matched on temperature bin
    off_by_temp = {}
    for k, v in summary.items():
        c, t, r = k.split("|")
        if c == "motor_off":
            off_by_temp[t] = v
    contrib = {}
    for k, v in summary.items():
        c, t, r = k.split("|")
        if c != "motor_on" or t not in off_by_temp:
            continue
        base = off_by_temp[t]["channels"]
        contrib[f"{t}|{r}"] = {
            ch: {m: v["channels"][ch][m] - base[ch][m]
                 for m in v["channels"][ch] if ch in base and m in base[ch]}
            for ch in v["channels"] if ch in base}

    out = {"file": a.h5, "cells": summary, "motor_contribution": contrib}
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)

    print(f"{'cell':<28}{'n':>4}{'PV':>6}  " + "  ".join(f"{c:>10}" for c in
          sorted({c for r in summary.values() for c in r["channels"]})))
    chans = sorted({c for r in summary.values() for c in r["channels"]})
    for k, r in summary.items():
        pv = f"{r['pv_mean']:.0f}" if r["pv_mean"] is not None else "-"
        cols = "  ".join(f"{r['channels'][c]['rms']:>10.5f}" if c in r["channels"]
                         else f"{'-':>10}" for c in chans)
        print(f"{k:<28}{r['n_sweeps']:>4}{pv:>6}  {cols}")

    if contrib:
        print("\nmotor-bidrag (motor_on RMS minus motor_off RMS ved samme temperatur):")
        print(f"{'temp|rpm':<20}  " + "  ".join(f"{c:>10}" for c in chans))
        for k, r in contrib.items():
            cols = "  ".join(f"{r[c]['rms']:>10.5f}" if c in r else f"{'-':>10}" for c in chans)
            print(f"{k:<20}  {cols}")
    f.close()


if __name__ == "__main__":
    sys.exit(main())
