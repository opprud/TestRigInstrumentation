#!/usr/bin/env python3
"""Full-resolution (un-binned) SP + AE spectra, 600 vs 3000 rpm overlaid.

This is the script that produced the SP/AE spectra sent to Eskild (2026-10-21), the
independent cross-check of the log-binned pipeline report (tools/run_report.py).
It answers: with the rig shaft STATIONARY (motor turned 90 deg in the frame-path runs),
why is there so much on the slip ring? -> it is the VFD reaching the sensors
electrically (common-mode via the shared ground), not rotation.

Difference from tools/run_report.py:
  - run_report.py: Welch nperseg 65536 (~38 Hz), curves LOG-BINNED to ~650 pts for display.
  - this script:   Welch nperseg 500000 (5 Hz), NO binning -> narrow peak combs are visible.

USAGE
  Put the three raw scope_*.h5 files in one folder (they are in Azure container
  'eceherning' under each run id), then:

      pip install h5py scipy numpy matplotlib
      python sp_ae_spectra.py [folder]        # default: this script's own folder

  Writes into that folder:
      fig_SP.png, fig_AE.png            the overlaid spectra (3 panels each)
      SP_AE_spectra.html                self-contained report (figures + findings)

METHOD
  - For each run, pick the DRIVEN sweeps (telem_vfd_cmd_hz > 0.5); the drive-off run
    uses all sweeps as the electrically-quiet baseline. (rpm_meas reads 0 in these runs
    because the tacho is on the stationary rig shaft, so cmd_hz is the state indicator.)
  - Average the Welch periodogram (Hann, nperseg = full 500 k sweep = 5 Hz resolution)
    across up to 80 selected sweeps per run.
  - Channels: SP (CHAN3, slip ring) and AE (CHAN2, Kistler acoustic emission).
    Labels per ticket 0049 (UL=CHAN1 UL750, AE=CHAN2 Kistler, SP=CHAN3 slip ring).

Edit RUNS below if your run ids differ.
"""
import sys, os, base64, html
import numpy as np
import h5py
from scipy.signal import welch
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

# tag -> (h5 filename, legend label, colour)
RUNS = [
    ("off",  "scope_20261020_132108.h5", "drev slukket (baseline)",          "#8a8a8a"),
    ("600",  "scope_20261020_140127.h5", "motor 600 rpm  (udgang 10 Hz)",    "#1f6fb2"),
    ("3000", "scope_20261020_143245.h5", "motor ~2975 rpm  (udgang 50 Hz)",  "#c0392b"),
]
CHANS   = ["SP", "AE"]
FS      = 2_500_000.0     # 2.5 MHz, also read per-sweep from the file
NPERSEG = 500_000         # full sweep -> 5 Hz resolution, no binning
MAXSW   = 80              # cap selected sweeps per run (speed)

def cmd_hz(g):
    for k in ("telem_vfd_cmd_hz","telem_cmd_hz","vfd_cmd_hz"):
        if k in g.attrs: return float(g.attrs[k])
    return None

def analyse(path):
    f = h5py.File(path, "r")
    sw = f["sweeps"]; names = sorted(sw.keys(), key=lambda s:int(s.split("_")[1]))
    cmds = np.array([np.nan if cmd_hz(sw[n]) is None else cmd_hz(sw[n]) for n in names])
    nz = cmds[(~np.isnan(cmds)) & (cmds > 0.5)]
    if nz.size:                                   # a driven run: keep sweeps at the modal speed
        modal = np.median(nz)
        sel = [i for i,c in enumerate(cmds) if (not np.isnan(c)) and abs(c-modal) <= 0.6]
    else:                                         # drive-off baseline: all sweeps
        sel, modal = list(range(len(names))), np.nan
    if len(sel) > MAXSW:
        sel = sorted(set(np.linspace(0, len(sel)-1, MAXSW).astype(int)))
    out = {"cmd": modal, "n": len(sel), "psd": {}}
    for ch in CHANS:
        acc = None
        for i in sel:
            v  = sw[names[i]][ch]["voltage"][:]
            fs = float(sw[names[i]][ch].attrs.get("sample_rate", FS))
            fr, P = welch(v, fs=fs, nperseg=NPERSEG, window="hann", detrend="constant")
            acc = P if acc is None else acc + P
        out["psd"][ch] = (fr, acc/len(sel))
    f.close()
    return out

def make_fig(res, ch, title, outdir):
    fig, ax = plt.subplots(3, 1, figsize=(11, 12))
    for tag,_,lab,c in [(t,fn,lab,c) for (t,fn,lab,c) in RUNS]:
        f,p = res[tag]["psd"][ch]; m = f >= 5
        ax[0].loglog(f[m], p[m], c=c, lw=0.7, label=lab)
    ax[0].set_title(f"{title} - fuldt spektrum (5 Hz - 1,25 MHz)", loc="left", fontsize=11)
    for tag,_,lab,c in RUNS:
        f,p = res[tag]["psd"][ch]; m = (f>=0)&(f<=200)
        ax[1].semilogy(f[m], p[m], c=c, lw=1.0, label=lab)
    for lh in range(50,201,50): ax[1].axvline(lh, color="#aaaaaa", ls=":", lw=.8)
    for mh in range(10,201,10): ax[1].axvline(mh, color="#d9b3b3", ls=":", lw=.5, zorder=0)
    ax[1].set_title("Zoom 0-200 Hz  (grå stiplet = 50 Hz net · lys rød = 10 Hz motor-kam)", loc="left", fontsize=11)
    for tag,_,lab,c in RUNS:
        f,p = res[tag]["psd"][ch]; m = (f>=3000)&(f<=12000)
        ax[2].semilogy(f[m], p[m], c=c, lw=0.8, label=lab)
    ax[2].axvline(4665, color="#444", ls="--", lw=1.0)
    ax[2].set_title("Zoom 3-12 kHz  (VFD switch-frekvens + sidebaand)", loc="left", fontsize=11)
    for a in ax:
        a.set_xlabel("Hz"); a.set_ylabel("PSD (V^2/Hz)"); a.grid(True, which="both", alpha=.25); a.legend(fontsize=8)
    fig.tight_layout()
    p = os.path.join(outdir, f"fig_{ch}.png"); fig.savefig(p, dpi=140); plt.close(fig)
    return p

def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    res = {}
    for tag, fn, _lab, _c in RUNS:
        path = os.path.join(outdir, fn)
        if not os.path.exists(path):
            sys.exit(f"mangler {path} - laeg de tre scope_*.h5 filer i {outdir}")
        res[tag] = analyse(path)
        print(f"{tag}: cmd_hz~{res[tag]['cmd']}, {res[tag]['n']} sweeps")
    psp = make_fig(res, "SP", "SP - slaebering (CHAN3)", outdir)
    pae = make_fig(res, "AE", "AE - Kistler acoustic emission (CHAN2)", outdir)
    def b64(p): return "data:image/png;base64," + base64.b64encode(open(p,"rb").read()).decode()
    doc = ("<!doctype html><meta charset='utf-8'><title>SP &amp; AE spectra</title>"
           "<body style='font-family:Arial;max-width:1040px;margin:auto;padding:16px'>"
           "<h1>SP &amp; AE spektre - fuld oploesning (un-binned)</h1>"
           "<p>Rig-aksel i ro (motor drejet 90 grader). Welch, 5 Hz, Hann, op til 80 drevne sweeps/koersel. "
           "SP-aktiviteten = VFD elektrisk (udgangs-kam der skalerer + ~4,7 kHz switch); AE 50/100 Hz = net-brum.</p>"
           f"<h2>SP - slaebering (CHAN3)</h2><img style='width:100%' src='{b64(psp)}'>"
           f"<h2>AE - Kistler acoustic emission (CHAN2)</h2><img style='width:100%' src='{b64(pae)}'>"
           "</body>")
    hp = os.path.join(outdir, "SP_AE_spectra.html"); open(hp,"w",encoding="utf-8").write(doc)
    print("skrev:", psp, pae, hp)

if __name__ == "__main__":
    main()
