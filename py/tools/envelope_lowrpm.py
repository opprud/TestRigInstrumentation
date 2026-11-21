"""Envelope/impulsiveness check of the low-rpm 'ball swish' (Kim, Tests 7/8).
Usage: envelope_lowrpm.py <run.h5> <out.json>
Picks sweeps by rpm (0, ~91, ~193, ~393, ~593) and temperature, and for AE and UL computes on the raw and on
band-passed Hilbert envelopes: kurtosis, crest factor, #bursts > mean+6 sd, peak position. Also the OE mic captures.
A sweep is 0.1 s: at ~91 rpm that is 0.15 shaft revolution, so a once-per-rev event cannot be resolved in one sweep.
"""
import json, sys
import h5py, numpy as np
from scipy.signal import butter, sosfiltfilt, hilbert

BANDS = {"AE": {"raw": None, "80-120k": (8e4, 1.2e5), "10-50k": (1e4, 5e4)},
         "UL": {"raw": None, "10-50k": (1e4, 5e4), "1-10k": (1e3, 1e4)}}


def stats(x):
    x = x - x.mean()
    s = x.std()
    k = float(np.mean(x ** 4) / s ** 4) if s > 0 else np.nan
    return s, k, float(np.abs(x).max() / s) if s > 0 else np.nan


def feat(v, dt, band):
    if band is None:
        x = v - v.mean()
    else:
        sos = butter(4, band, btype="band", fs=1 / dt, output="sos")
        x = sosfiltfilt(sos, v - v.mean())
    env = np.abs(hilbert(x))
    s, k, cf = stats(x)
    e = env[:len(env) // 50 * 50].reshape(-1, 50).mean(1)          # 10 us bins
    thr = e.mean() + 6 * e.std()
    above = e > thr
    nb = int(np.sum(np.diff(above.astype(int)) == 1) + above[0])
    return {"rms": float(s), "kurt": k, "crest": cf, "env_kurt": float(np.mean((e - e.mean()) ** 4) / e.std() ** 4),
            "env_max_over_mean": float(e.max() / e.mean()), "bursts6s": nb}


def main():
    path, out = sys.argv[1], sys.argv[2]
    res = {"sweeps": [], "oe": []}
    targets = [(0, 3), (91, 25), (193, 25), (393, 25), (593, 25)]
    with h5py.File(path, "r") as f:
        sw = f["sweeps"]
        for k in sorted(sw):
            a = sw[k].attrs
            rpm, T = float(a.get("telem_rpm_meas", np.nan)), float(a.get("telem_omron_pv_c", np.nan))
            if not any(abs(rpm - t) <= tol for t, tol in targets):
                continue
            if rpm < 1 and T > 36:
                continue
            tgt = min((t for t, _ in targets), key=lambda t: abs(rpm - t))
            r = {"k": k, "tick": float(a["tick"]), "rpm": rpm, "T": T, "tgt": tgt}
            for ch, bands in BANDS.items():
                v = sw[k][ch]["voltage"][:].astype(float)
                dt = float(sw[k][ch].attrs["x_increment"])
                r[ch] = {b: feat(v, dt, bb) for b, bb in bands.items()}
            res["sweeps"].append(r)
        if "oe_samples" in f:
            for k in sorted(f["oe_samples"])[:12]:
                g = f["oe_samples"][k]
                rec = {"k": k, "tick": float(g.attrs["tick_start"]), "rpm": float(g.attrs.get("telem_rpm_meas", np.nan))}
                for ch in g:
                    v = g[ch][:].astype(float)
                    fs = float(g[ch].attrs.get("sample_rate_hz", 80000))
                    v = v - v.mean()
                    sos = butter(4, (5e3, 30e3), btype="band", fs=fs, output="sos")
                    env = np.abs(hilbert(sosfiltfilt(sos, v)))
                    env = env - env.mean()
                    sp = np.abs(np.fft.rfft(env * np.hanning(len(env)))) ; fr = np.fft.rfftfreq(len(env), 1 / fs)
                    m = (fr > 1) & (fr < 100)
                    top = np.argsort(sp[m])[::-1][:5]
                    rec[ch] = {"rms": float(v.std()), "kurt": float(np.mean(v ** 4) / v.var() ** 2), "n": len(v), "dur_s": len(v) / fs,
                               "env_peaks_hz": [round(float(fr[m][i]), 2) for i in top], "env_peaks_rel": [round(float(sp[m][i] / np.median(sp[m])), 1) for i in top]}
                res["oe"].append(rec)
    json.dump(res, open(out, "w"))
    print("sweeps", len(res["sweeps"]), "oe", len(res["oe"]))


if __name__ == "__main__":
    main()
