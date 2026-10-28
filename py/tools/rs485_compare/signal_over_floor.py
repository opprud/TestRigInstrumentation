from common import *
A=load('A_manual.npz'); B=load('B_modbus.npz'); cA=cells(A); cB=cells(B)
STEP={'UL':0.4/199,'AE':4.0/199}
print("quantisation-noise variance step^2/12 over 0-2.5 MHz vs measured rest variance (settled 0 rpm):")
for c in ('UL','AE'):
    q=STEP[c]**2/12
    out=[f"{n}: {np.median(np.array(bandpow(d,c)[(cc[1]==0)&cc[3]].sum(1))):.2e} V^2 ({10*np.log10(np.median(bandpow(d,c)[(cc[1]==0)&cc[3]].sum(1))/q):+.1f} dB over quant.)" for n,d,cc in (('A',A,cA),('B',B,cB))]
    print(f"  {c}: step {STEP[c]*1e3:.1f} mV -> quant. var {q:.2e} V^2 | "+" | ".join(out))
def snr(d,cc,c,r,j):
    bp=bandpow(d,c)[:,j]; fl=np.median(bp[(cc[1]==0)&cc[3]]); sg=np.median(bp[(cc[1]==r)&cc[3]]); return 10*np.log10(sg/fl)
for c in ('UL','AE'):
    print(f"\n=== {c}: signal over standstill floor (dB) per band, A manual / B RS485 -- below ~3 dB the band is effectively drowned ===")
    print('band'.ljust(11)+''.join(f'{r:>16}' for r in (600,1800,3000)))
    for j,bd in enumerate(BANDS):
        row=bname(bd).ljust(11)
        for r in (600,1800,3000): row+=f"{snr(A,cA,c,r,j):7.1f} /{snr(B,cB,c,r,j):6.1f}  "
        print(row)
