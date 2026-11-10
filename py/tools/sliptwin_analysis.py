"""Per-sweep SP/UL/AE statistics for the slip-ring twin comparison (run 1 vs run 2).

Usage: sliptwin_analysis.py <run.h5> <out.json> [stride=3]
Per sweep: telem rpm/temp/mass, and for each channel mean, AC rms and band rms
(0-10, 10-50, 50-100, 100-200, 200-2500 kHz) from one rfft of the 500 k points.
"""
import json
import sys
from multiprocessing import Pool

import h5py
import numpy as np

BANDS = [(0, 1e4), (1e4, 5e4), (5e4, 1e5), (1e5, 2e5), (2e5, 2.5e6)]
CH = ("SP", "UL", "AE")


def one(args):
    path, k = args
    with h5py.File(path, "r") as f:
        g = f["sweeps"][k]
        a = g.attrs
        r = {"k": k, "rpm": float(a.get("telem_rpm_meas", np.nan)), "T": float(a.get("telem_omron_pv_c", np.nan)),
             "sv": float(a.get("telem_omron_sv_c", np.nan)), "mass": float(a.get("telem_mass_g", np.nan)),
             "t": float(a.get("tick", np.nan))}
        for c in CH:
            v = g[c]["voltage"][:].astype(float)
            dt = float(g[c].attrs["x_increment"])
            r[c + "_mean"] = float(v.mean())
            x = v - v.mean()
            r[c + "_rms"] = float(x.std())
            spec = np.abs(np.fft.rfft(x)) / len(x)
            fr = np.fft.rfftfreq(len(x), dt)
            r[c + "_bands"] = [float(np.sqrt(2 * np.sum(spec[(fr >= lo) & (fr < hi)] ** 2))) for lo, hi in BANDS]
    return r


if __name__ == "__main__":
    path, out = sys.argv[1], sys.argv[2]
    stride = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    with h5py.File(path, "r") as f:
        ks = sorted(f["sweeps"])[::stride]
    with Pool(3) as p:
        res = p.map(one, [(path, k) for k in ks], chunksize=8)
    json.dump(res, open(out, "w"))
    print("done", len(res))
