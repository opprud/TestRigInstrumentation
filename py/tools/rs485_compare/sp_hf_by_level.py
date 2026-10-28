from common import *
A=load('A_manual.npz'); B=load('B_modbus.npz'); cA=cells(A); cB=cells(B); j=len(BANDS)-1; fl=1170e-6
print("0-rpm stops: per SV level -> PV-SV (median, C) and SP 1-2.5 MHz x floor (median)")
for L in (40,55,70,85,100):
    row=[]
    for n,d,c_ in (('A',A,cA),('B',B,cB)):
        t=c_[0]; m=(c_[1]==0)&(c_[2]==L)&(t['tick']>300)   # stops at end of staircases
        if L==40: m=(c_[1]==0)&(c_[2]==L)&(t['tick']>300)
        if m.sum()==0: row.append(f"{n}: n/a"); continue
        bp=bandpow(d,'SP')[:,j]/fl; pv=t['telem_omron_pv_c']-t['telem_temp_target']
        row.append(f"{n}: n={m.sum():2d} PV-SV {np.median(pv[m]):+5.1f} (min {pv[m].min():+.0f}, max {pv[m].max():+.0f})  x{np.median(bp[m]):.1f}")
    print(f"  SV {L:3d}:  "+"   |   ".join(row))
