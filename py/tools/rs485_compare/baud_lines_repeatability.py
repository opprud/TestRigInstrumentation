from common import *
from scipy.ndimage import median_filter
A=load('A_manual.npz'); B=load('B_modbus.npz'); f=A['freq']
cA=cells(A); cB=cells(B)
def mpsd(d,c,m): return d[f'{c}_psd'][m].astype(np.float64).mean(0)
def prom_at(P,f0,hw=60):
    w=(f>f0-hw)&(f<f0+hw); fl=(f>f0-1500)&(f<f0+1500)&~((f>f0-400)&(f<f0+400)); return 10*np.log10(P[w].max()/np.median(P[fl]))
print("=== RS485 baud-related frequencies (9600 baud: 4.8k / 9.6k / 14.4k / 19.2k) + VFD carrier 4.66k: line prominence over local floor, dB ===")
print("            rpm   freq     A off   B on")
for c in CH:
    for r in (0,3000):
        mA=(cA[1]==r)&cA[3]; mB=(cB[1]==r)&cB[3]; PA,PB=mpsd(A,c,mA),mpsd(B,c,mB)
        print(f"  {c}  {r:5d}  "+"  ".join(f"{f0/1e3:.2f}k: {prom_at(PA,f0):4.1f}/{prom_at(PB,f0):4.1f}" for f0 in (4660,4800,9600,14400,19200)))
print("\n=== lines to 2.5 MHz differing >6 dB (0 rpm and 3000 rpm) ===")
def prom(P): return 10*np.log10(P/median_filter(P,size=301,mode='nearest'))
for r in (0,3000):
    for c in CH:
        mA=(cA[1]==r)&cA[3]; mB=(cB[1]==r)&cB[3]; PA,PB=mpsd(A,c,mA),mpsd(B,c,mB); pa,pb=prom(PA),prom(PB)
        d=pb-pa; idx=np.where((f>1e3)&(np.abs(d)>6))[0]
        g=[]; 
        for i in idx:
            if g and i-g[-1][-1]<=3: g[-1].append(i)
            else: g.append([i])
        res=sorted([(abs(d[x[np.argmax(np.abs(d[x]))]]),f[x[np.argmax(np.abs(d[x]))]],pa[x[np.argmax(np.abs(d[x]))]],pb[x[np.argmax(np.abs(d[x]))]]) for x in g],reverse=True)[:6]
        print(f"  {c} {r:4d} rpm: "+("; ".join(f"{fr/1e3:.1f}k (A {x:.0f}/B {y:.0f} dB)" for _,fr,x,y in res) if res else 'none'))
print("\n=== within-run repeatability: up-staircase vs down-staircase, same SV & speed, band-power dB (std over cells) vs the A-vs-B difference ===")
def phase(d):
    t=dict(zip(d['tel_names'],d['tel'].T)); tk=t['telem_tick'] if 'telem_tick' in t else t['tick']
    k0=np.where(t['telem_rpm_target']>0)[0][0]; off=tk[k0]-126; m=np.floor(((tk-off-120)%600)/60); return m
for n,d,cc in (('A off',A,cA),('B on ',B,cB)):
    ph=phase(d); up=ph<=3; dn=(ph>=5)&(ph<=8)
    for c in ('UL','AE','SP'):
        bp=bandpow(d,c); out=[]
        for j,bd in enumerate(BANDS):
            ds=[]
            for L in (40,55,70,85,100):
                for r in (600,1200,1800,2400):
                    mu=(cc[1]==r)&(cc[2]==L)&cc[3]&up; md=(cc[1]==r)&(cc[2]==L)&cc[3]&dn
                    if mu.sum()>=2 and md.sum()>=2: ds.append(10*np.log10(np.median(bp[md,j])/np.median(bp[mu,j])))
            out.append((np.mean(ds),np.std(ds)))
        print(f"  {n} {c}: down-vs-up mean dB by band: "+" ".join(f"{m:+.1f}" for m,_ in out)+f"   | cell scatter (std) median {np.median([s for _,s in out]):.1f} dB")
