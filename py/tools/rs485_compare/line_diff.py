from common import *
from scipy.ndimage import median_filter
A=load('A_manual.npz'); B=load('B_modbus.npz'); f=A['freq']
tA,rA,sA,stA=cells(A); tB,rB,sB,stB=cells(B)
def meanpsd(d,c,m): return d[f'{c}_psd'][m].astype(np.float64).mean(0)
def prom(P):   # peak prominence over running-median floor, dB
    fl=median_filter(P,size=301,mode='nearest'); return 10*np.log10(P/fl)
def lines(c,rbin,fmax=1e6,thr=6.0,top=12):
    mA=(rA==rbin)&stA; mB=(rB==rbin)&stB
    PA,PB=meanpsd(A,c,mA),meanpsd(B,c,mB); pa,pb=prom(PA),prom(PB)
    sel=(f>200)&(f<fmax)
    # features that are lines in one run but not the other
    diff=pb-pa
    idx=np.where(sel&(np.abs(diff)>thr))[0]
    # collapse neighbouring bins
    groups=[]; 
    for i in idx:
        if groups and i-groups[-1][-1]<=3: groups[-1].append(i)
        else: groups.append([i])
    res=[]
    for g in groups:
        k=g[np.argmax(np.abs(diff[g]))]; res.append((abs(diff[k]),f[k],pa[k],pb[k],10*np.log10(PB[k]/PA[k])))
    res.sort(reverse=True)
    print(f"\n--- {c} @ {rbin} rpm  (n A={mA.sum()}, B={mB.sum()}); line-prominence differs >{thr} dB ---")
    if not res: print('  none'); return
    print('  freq(Hz)   prom_A(dB) prom_B(dB)  level B/A(dB)')
    for _,fr,x,y,l in res[:top]: print(f"  {fr:9.0f}   {x:7.1f}   {y:7.1f}     {l:+6.1f}")
    print(f"  ({len(res)} features total)")
for rb_ in (0,3000):
    for c in CH: lines(c,rb_)
