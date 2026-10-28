from common import *
from scipy.ndimage import median_filter
A=load('A_manual.npz'); B=load('B_modbus.npz'); f=A['freq']
def prom_sweeps(d,c,f0,hw,floor_hw=3000):
    P=d[f'{c}_psd'].astype(np.float64)
    w=(f>f0-hw)&(f<f0+hw); fl=(f>f0-floor_hw)&(f<f0+floor_hw)&~((f>f0-3*hw)&(f<f0+3*hw))
    pk=P[:,w].max(1); fn=np.median(P[:,fl],1); k=np.argmax(P[:,w],1); return 10*np.log10(pk/fn), f[w][k]
for c,f0,hw in (('UL',1068,80),('AE',343933,400)):
    print(f"\n=== {c} line near {f0} Hz: peak over local floor per sweep (dB) ===")
    for n,d in (('A off',A),('B on ',B)):
        t,rb,sv,st=cells(d)
        for r in (0,600,1800,3000):
            m=(rb==r)&st; p,fq=prom_sweeps(d,c,f0,hw)
            x=p[m]; print(f"  {n} rpm {r:4d}: n={m.sum():2d} median {np.median(x):5.1f}  min {x.min():5.1f} max {x.max():5.1f} | >6 dB in {(x>6).sum()}/{m.sum()} | freq med {np.median(fq[m]):.0f}")
    # time order at 0 rpm for B vs A
    for n,d in (('A off',A),('B on ',B)):
        t,rb,sv,st=cells(d); m=(rb==0)&st; p,_=prom_sweeps(d,c,f0,hw)
        print(f"  {n} 0 rpm by SV:", {int(L):round(float(np.median(p[m&(sv==L)])),1) for L in (25,40,55,70,85,100) if (m&(sv==L)).sum()>0})
