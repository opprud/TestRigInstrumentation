#!/usr/bin/env python3
"""Generate an FFT report + note for a run, and optionally upload both to Azure.

    python3 tools/run_report.py <run_id> [<run_id> ...] [--upload]

Writes into each run's own folder, so the uploader picks them up as sidecars:
    spectra_<run_id>.html   self-contained log-log spectra for UL / AE / SP
    NOTE_<run_id>.txt       what the run was, what the curves show, what they do not

The spectra use the same method as docs/0046_noise_floor.csv so the numbers can be laid
beside the ticket-0046 reference: Welch, Hanning, nperseg 65536, DC removed, density
scaling integrated per band (so the bands sum to the broadband RMS).
"""
import sys, os, json, glob, html
import numpy as np
from scipy.signal import welch

BANDS = [("0-10k",0,10e3),("10-50k",10e3,50e3),("50-100k",50e3,100e3),
         ("100-126k",100e3,126e3),("126-135k",126e3,135e3),("135-500k",135e3,500e3),
         ("500k-1M",500e3,1e6),("1055-1066k",1055e3,1066e3),("1M-1.25M",1e6,1.25e6)]
CH = ("UL","AE","SP")
SENSOR = {"UL":"Kistler acoustic emission (CHAN1)","AE":"piezo accelerometer (CHAN2)",
          "SP":"slip ring (CHAN3)"}
NBINS, NSWEEP = 650, 16
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def analyse(run):
    import h5py
    d = os.path.join(ROOT,"data","runs",run)
    f = glob.glob(os.path.join(d,"*.h5"))
    if not f: return None
    rec = {"run":run,"dir":d,"ch":{}}
    tj = glob.glob(os.path.join(d,"telemetry_*.jsonl"))
    if tj:
        try: rec["profile"] = json.loads(open(tj[0]).readline()).get("profile_name","")
        except Exception: pass
    st = os.path.join(d,"RIG_STATE.txt")
    rec["state"] = open(st).read() if os.path.exists(st) else None
    with h5py.File(f[0],"r") as h:
        sw = sorted(h["/sweeps"].keys(), key=lambda s:int(s.split("_")[1]))
        rec["sweeps"] = len(sw)
        idx = np.unique(np.linspace(0,len(sw)-1,min(NSWEEP,len(sw))).astype(int))
        rec["n"] = len(idx)
        a0 = h["/sweeps"][sw[0]].attrs
        rec["rpm"] = sorted({round(float(h["/sweeps"][k].attrs.get("telem_rpm_target") or 0))
                             for k in sw})
        ss = h.get("/metadata/scope_settings")
        for ch in CH:
            if ch not in h["/sweeps"][sw[0]]: continue
            P=None; fr=None; rms=[]; dc=[]
            for i in idx:
                g = h["/sweeps"][sw[i]][ch]
                v = np.asarray(g["voltage"],dtype=np.float64); fs=float(g.attrs["sample_rate"])
                rms.append(v.std()); dc.append(v.mean())
                fr,p = welch(v-v.mean(),fs=fs,nperseg=65536,scaling="density")
                P = p if P is None else P+p
            P/=len(idx); df=fr[1]-fr[0]
            probe=None
            if ss is not None and ch in ss:
                for k in ss[ch].attrs:
                    if "prob" in k.lower(): probe=float(ss[ch].attrs[k])
            m = fr>=20
            lf=np.log10(fr[m]); edges=np.linspace(lf.min(),lf.max(),NBINS+1)
            bi=np.digitize(lf,edges)-1
            xs=[];ys=[]
            for b in range(NBINS):
                s=(bi==b)
                if s.any():
                    xs.append(float(10**((edges[b]+edges[b+1])/2)))
                    ys.append(float(np.sqrt(P[m][s].mean()*df)))
            rec["fs"]=fs
            rec["ch"][ch]=dict(rms=float(np.mean(rms)),dc=float(np.mean(dc)),probe=probe,
                x=xs,y=ys,bands={nm:float(np.sqrt(P[(fr>=lo)&(fr<hi)].sum()*df))
                                 for nm,lo,hi in BANDS})
    return rec

def reference():
    p=os.path.join(ROOT,"docs","0046_noise_floor.json")
    if not os.path.exists(p): return {}
    return {r["block"]:r for r in json.load(open(p))}

def write_note(rec, ref):
    r=rec["run"]; L=[]
    L.append(f"FFT REPORT NOTE — run {r}")
    L.append("="*70); L.append("")
    if rec.get("profile"): L.append(f"Profile      {rec['profile']}")
    L.append(f"Sweeps       {rec['sweeps']} (spectra averaged over {rec['n']} spread across the run)")
    L.append(f"rpm targets  {', '.join(str(x) for x in rec['rpm'])}")
    L.append("")
    L.append("CHANNEL LEVELS")
    L.append(f"  {'ch':4}{'sensor':36}{'AC rms V':>10}{'mean V':>9}{'probe':>7}")
    for ch in CH:
        c=rec["ch"].get(ch)
        if not c: continue
        L.append(f"  {ch:4}{SENSOR[ch]:36}{c['rms']:10.5f}{c['dc']:+9.3f}"
                 f"{('x%g'%c['probe']) if c['probe'] else '   ?':>7}")
    L.append("")
    nyq = rec.get("fs",2.5e6)/2
    L.append(f"Sample rate  {rec.get('fs',0)/1e3:.0f} kHz  ->  Nyquist {nyq/1e3:.0f} kHz")
    L.append("")
    L.append("BAND LEVELS (V rms in band; bands sum to the broadband RMS)")
    L.append("  Bands entirely above Nyquist are marked '-'. There is no content there to")
    L.append("  measure: that is a property of this run's sample rate, not a failed measurement.")
    L.append(f"  {'band':14}"+"".join(f"{ch:>12}" for ch in CH))
    for nm,_,_ in BANDS:
        if dict((b[0],b[1]) for b in BANDS)[nm] >= nyq:
            L.append(f"  {nm:14}"+"".join(f"{'-':>12}" for _ in CH)); continue
        L.append(f"  {nm:14}"+"".join(
            f"{rec['ch'][ch]['bands'][nm]:12.6f}" if ch in rec["ch"] else f"{'-':>12}" for ch in CH))
    L.append("")
    b2b=ref.get("B2B")
    if b2b:
        L.append("AGAINST THE TICKET-0046 COUPLED FLOOR (block 2B, run 20260930_112905)")
        for ch in CH:
            c=rec["ch"].get(ch); f=b2b["channels"].get(ch)
            if c and f:
                L.append(f"  {ch}: {f['ac_rms_V']:.5f} -> {c['rms']:.5f} V   = {c['rms']/f['ac_rms_V']:.2f}x")
        L.append("")
    L.append("METHOD")
    L.append("  Welch periodogram, Hanning, nperseg 65536, DC removed, scaling='density'")
    L.append("  integrated over each band, so the bands sum to the broadband RMS. Same method as")
    L.append("  docs/0046_noise_floor.csv, so these numbers can be laid directly beside that reference.")
    L.append("  Curves in the HTML are log-binned to ~650 points per channel for display only.")
    L.append("")
    if rec.get("state"):
        L.append("RIG STATE (from RIG_STATE.txt in this run folder)")
        for ln in rec["state"].strip().splitlines(): L.append("  "+ln)
    else:
        L.append("RIG STATE  not recorded for this run — no RIG_STATE.txt in the folder.")
    return "\n".join(L)+"\n"

def write_html(rec):
    data=json.dumps({ch:{"x":c["x"],"y":c["y"],"rms":c["rms"],"dc":c["dc"],"probe":c["probe"]}
                     for ch,c in rec["ch"].items()},separators=(",",":"))
    bands=json.dumps({ch:c["bands"] for ch,c in rec["ch"].items()},separators=(",",":"))
    t=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"_report_template.html")).read()
    return (t.replace("__RUN__",html.escape(rec["run"]))
             .replace("__PROFILE__",html.escape(rec.get("profile") or ""))
             .replace("__SWEEPS__",str(rec["sweeps"])).replace("__N__",str(rec["n"]))
             .replace("__RPM__",html.escape(", ".join(str(x) for x in rec["rpm"])))
             .replace("__DATA__",data).replace("__BANDS__",bands)
             .replace("__NYQ__","%.0f"%(rec.get("fs",2.5e6)/2e3)))

def main():
    args=[a for a in sys.argv[1:] if not a.startswith("--")]
    up="--upload" in sys.argv
    ref=reference()
    for run in args:
        rec=analyse(run)
        if not rec: print(f"{run}: no h5, skipped"); continue
        note=write_note(rec,ref)
        np_=os.path.join(rec["dir"],f"NOTE_{run}.txt"); open(np_,"w").write(note)
        hp=os.path.join(rec["dir"],f"spectra_{run}.html"); open(hp,"w").write(write_html(rec))
        print(f"{run}: {os.path.basename(np_)} + {os.path.basename(hp)}")
        if up:
            os.system(f'cd {ROOT}/py && .venv/bin/python tools/upload_to_azure.py '
                      f'data/runs/{run} --container eceherning --log /tmp/report_upload.log >/dev/null 2>&1')
            print(f"   uploaded {run}/ to eceherning")
if __name__=="__main__": main()
