from common import *
A=load('A_manual.npz'); B=load('B_modbus.npz'); cA=cells(A); cB=cells(B); j=len(BANDS)-1; fl=1170e-6
for n,d,c_ in (('A off',A,cA),('B on ',B,cB)):
    t=c_[0]; rb=c_[1]; bp=bandpow(d,'SP')[:,j]/fl; m=(rb==0)
    print(f"\n{n} 0-rpm sweeps, SP 1-2.5 MHz x floor, in time order (tick: x):")
    print('  '+'  '.join(f"{t['tick'][i]:.0f}:{bp[i]:.1f}" for i in np.where(m)[0]))
    print(f"  median {np.median(bp[m]):.2f}  mean {bp[m].mean():.2f}  >2x: {(bp[m]>2).sum()}/{m.sum()}")
