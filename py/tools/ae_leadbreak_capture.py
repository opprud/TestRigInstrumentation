"""Single-shot AE (CHAN2) capture of a pencil-lead break (Hsu-Nielsen) as a reference scope picture.
Usage: ae_leadbreak_capture.py <out_prefix> [level_v=0.2] [wait_s=180]
Arms a NORMAL/SINGLE edge trigger on CHAN2 (either slope), waits for the break, reads CHAN2 RAW,
saves <out_prefix>.npz (+ .png if matplotlib), then restores the trigger it found. Channel/timebase untouched.
"""
import socket, sys, time
import numpy as np

IP = ("169.254.227.43", 5025)


def conn():
    s = socket.create_connection(IP, 10); s.settimeout(20); return s

def w(s, c): s.sendall((c + "\n").encode())

def q(s, c):
    w(s, c); d = b""
    while not d.endswith(b"\n"): d += s.recv(65536)
    return d.decode().strip()

def qbin(s, c):
    w(s, c); h = b""
    while len(h) < 2: h += s.recv(2 - len(h))
    n = int(h[1:2]); ln = b""
    while len(ln) < n: ln += s.recv(n - len(ln))
    ln = int(ln); b = b""
    while len(b) < ln + 1: b += s.recv(min(1 << 20, ln + 1 - len(b)))
    return b[:ln]

out = sys.argv[1]; lev = float(sys.argv[2]) if len(sys.argv) > 2 else 0.2; wait = float(sys.argv[3]) if len(sys.argv) > 3 else 180
s = conn()
old = {k: q(s, k + "?") for k in [":TRIG:EDGE:SLOP", ":TRIG:EDGE:LEV", ":TRIG:SWE", ":TRIG:EDGE:SOUR", ":TIM:POS"]}
print("saved", old, flush=True)
try:
    w(s, ":TRIG:EDGE:SOUR CHAN2"); w(s, ":TRIG:EDGE:SLOP EITH"); w(s, f":TRIG:EDGE:LEV {lev}")
    w(s, ":TRIG:SWE NORM"); w(s, ":TIM:POS 0"); w(s, ":SING")
    print("ARMED", time.strftime("%H:%M:%S"), flush=True)
    t0 = time.time(); got = False
    while time.time() - t0 < wait:
        time.sleep(0.5)
        if int(q(s, ":OPER:COND?")) & 8 == 0:   # bit 3 = running
            got = True; break
    print("triggered" if got else "TIMEOUT", time.strftime("%H:%M:%S"), flush=True)
    if got:
        w(s, ":WAV:SOUR CHAN2"); w(s, ":WAV:FORM WORD"); w(s, ":WAV:UNS 0"); w(s, ":WAV:BYT MSBF"); w(s, ":WAV:POIN:MODE RAW"); w(s, ":WAV:POIN MAX")
        pre = q(s, ":WAV:PRE?").split(",")
        raw = qbin(s, ":WAV:DATA?")
        y = np.frombuffer(raw, dtype=">i2").astype(float)
        dx, x0, yinc, yor, yref = float(pre[4]), float(pre[5]), float(pre[7]), float(pre[8]), float(pre[9])
        v = (y - yref) * yinc + yor; t = x0 + np.arange(len(v)) * dx
        rng = q(s, ":CHAN2:RANG?"); offs = q(s, ":CHAN2:OFFS?"); tr = q(s, ":TIM:RANG?")
        np.savez_compressed(out + ".npz", t=t, v=v, dt=dx, chan2_range=rng, chan2_offset=offs, timebase_range=tr, trig_level=lev,
                            captured=time.strftime("%Y-%m-%d %H:%M:%S"))
        i = int(np.argmax(np.abs(v - np.median(v))))
        print(f"n={len(v)} dt={dx:.3e} Vpp={v.max()-v.min():.3f} peak={v[i]:.3f}V at t={t[i]*1e3:.3f} ms rest_rms={v[:len(v)//20].std():.4f}", flush=True)
        try:
            import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
            fig, ax = plt.subplots(2, 1, figsize=(11, 7))
            ax[0].plot(t * 1e3, v, lw=.5); ax[0].set_xlabel("ms"); ax[0].set_ylabel("AE V"); ax[0].set_title(f"AE (CHAN2) pencil-lead break, range {rng} V, {dx*1e9:.0f} ns/sample")
            lo = max(0, i - 2500); hi = min(len(v), i + 7500)
            ax[1].plot(t[lo:hi] * 1e6, v[lo:hi], lw=.6); ax[1].set_xlabel("us"); ax[1].set_ylabel("AE V")
            fig.tight_layout(); fig.savefig(out + ".png", dpi=110)
        except Exception as e:
            print("no png:", e)
finally:
    s2 = conn()
    for k, c in [(":TRIG:EDGE:SLOP", "SLOP"), (":TRIG:EDGE:LEV", "LEV"), (":TIM:POS", None)]:
        pass
    w(s2, f":TRIG:EDGE:SLOP {old[':TRIG:EDGE:SLOP']}"); w(s2, f":TRIG:EDGE:LEV {old[':TRIG:EDGE:LEV']}")
    w(s2, f":TIM:POS {old[':TIM:POS']}"); w(s2, f":TRIG:SWE {old[':TRIG:SWE']}"); w(s2, ":RUN")
    print("restored", {k: q(s2, k + "?") for k in old}, flush=True)
