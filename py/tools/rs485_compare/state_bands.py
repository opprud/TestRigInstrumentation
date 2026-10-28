"""Per-state band power for the stationary RS485 state test (rs485_state_test.py)."""
import sys, json, h5py, numpy as np
from scipy.signal import welch
run = sys.argv[1]
st = json.load(open(f"{run}/states.json"))["states"]
BANDS = [(500,1500),(1500,3000),(3000,6000),(6000,10000),(1e4,2e4),(2e4,5e4),(5e4,1e5),(1e5,2e5),(2e5,3.1e5)]
from datetime import datetime
ts = lambda s: datetime.fromisoformat(s).timestamp()
rows = {}
with h5py.File(next(__import__("pathlib").Path(run).glob("*.h5"))) as f:
    for k in sorted(f["sweeps"]):
        g = f["sweeps"][k]
        t = g.attrs.get("timestamp_utc")
        t = ts(t.decode() if isinstance(t, bytes) else str(t))
        idx = [i for i, s in enumerate(st) if ts(s["start_utc"]) <= t < ts(s["end_utc"])]
        if not idx: continue
        i = idx[0]
        for c in ("UL", "AE", "SP"):
            v = g[c]["voltage"][:].astype(np.float64); v -= v.mean()
            fs = g[c].attrs["sample_rate"]
            fr, P = welch(v, fs, nperseg=min(16384, len(v)))
            df = fr[1]-fr[0]
            rows.setdefault((i, c), []).append([P[(fr>=lo)&(fr<hi)].sum()*df for lo, hi in BANDS] + [v.std()])
print("band rms in uV (mean of sweeps); columns:", [f"{lo/1e3:g}-{hi/1e3:g}k" for lo, hi in BANDS], "total")
for c in ("SP", "UL", "AE"):
    print(c)
    for i, s in enumerate(st):
        a = np.array(rows.get((i, c), []))
        if not len(a): continue
        m = np.sqrt(a[:, :-1].mean(0))*1e6
        print(f"  {i} {s['state']:5s} n={len(a):2d} " + " ".join(f"{x:8.1f}" for x in m) + f"  tot={a[:,-1].mean()*1e6:9.1f}")
