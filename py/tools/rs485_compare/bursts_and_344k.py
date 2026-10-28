from common import *
A=load('A_manual.npz'); B=load('B_modbus.npz'); f=A['freq']
exec(open('a4.py').read().split("for c,f0,hw")[0].split("f=A['freq']")[1])
print("=== AE 344 kHz line vs heater state (0 rpm sweeps, both runs) ===")
for n,d in (('A off',A),('B on ',B)):
    t,rb,sv,st=cells(d); pv=t['telem_omron_pv_c']; p,_=prom_sweeps(d,'AE',343933,400)
    dpv=np.r_[0,np.diff(pv)]
    m=(rb==0)
    for lab,mm in (('heater calling (PV<SV-1)',m&(pv<sv-1)),('near SV (|PV-SV|<=1)',m&(np.abs(pv-sv)<=1)),('above SV (PV>SV+1, heater off)',m&(pv>sv+1))):
        if mm.sum(): print(f"  {n} {lab:32s} n={mm.sum():2d} median prom {np.median(p[mm]):5.1f} dB  >6dB: {(p[mm]>6).sum()}/{mm.sum()}")
print("\n=== time-domain bursts: 1 ms frame energy, max/median per sweep (0 rpm, settled) ===")
for band in ('b2_8k','b10_50k'):
    for c in CH:
        out=[]
        for n,d in (('A off',A),('B on ',B)):
            t,rb,sv,st=cells(d); m=(rb==0)&st; E=d[f'{c}_fe_{band}'][m]; r=E.max(1)/np.median(E,1)
            out.append(f"{n}: median max/med {np.median(r):4.1f}  p90 {np.percentile(r,90):4.1f}  >3x in {(r>3).sum()}/{m.sum()}")
        print(f"  {band:8s} {c}: "+' | '.join(out))
