from common import *
A=load('A_manual.npz'); B=load('B_modbus.npz'); f=A['freq']; df=f[1]-f[0]; cA=cells(A); cB=cells(B); jTop=len(BANDS)-1; FL=1170e-6
bpA,bpB=bandpow(A,'SP'),bandpow(B,'SP')
mA=(cA[1]==0)&(cA[0]['tick']>300); mB=(cB[1]==0)&(cB[0]['tick']>300)     # stops at ends of staircases (not the lead-in)
eB=mB&(bpB[:,jTop]/FL>1.3)
print(f"stop sweeps A: {mA.sum()}, B: {mB.sum()}, B flagged (SP 1-2.5 MHz > 1.3x floor): {eB.sum()}; A flagged: {(mA&(bpA[:,jTop]/FL>1.3)).sum()}")
print("\nwhere is the excess? mean PSD ratio B(flagged)/A(stops), SP, per 250 kHz slice:")
PA=A['SP_psd'][mA].astype(float).mean(0); PB=B['SP_psd'][eB].astype(float).mean(0)
for lo in np.arange(0,2.5e6,250e3):
    w=(f>=lo)&(f<lo+250e3); print(f"  {lo/1e3:6.0f}-{(lo+250e3)/1e3:5.0f} kHz: {10*np.log10(PB[w].sum()/PA[w].sum()):+5.1f} dB")
print("\nhow much does it matter for SP's own numbers at standstill (flagged B vs A stops)?")
for lab,m,bp,d in (('A stops',mA,bpA,A),('B flagged',eB,bpB,B)):
    var=(d['SP_rms'][m]**2); top=bp[m,jTop]; print(f"  {lab:10s}: SP rms {np.sqrt(var).mean():.4f} V (var {var.mean():.2e} V^2), 1-2.5 MHz part {top.mean():.2e} V^2 = {100*top.mean()/var.mean():.0f} % of variance, Vpp {d['SP_vpp'][m].mean():.3f} V")
lowB=bpB[eB,:jTop].sum(1); lowA=bpA[mA,:jTop].sum(1)
print(f"  SP variance below 1 MHz:  A {lowA.mean():.2e}  B(flagged) {lowB.mean():.2e}  ({10*np.log10(lowB.mean()/lowA.mean()):+.2f} dB)")
print(f"  => excess above 1 MHz = {(bpB[eB,jTop].mean()-bpA[mA,jTop].mean()):.2e} V^2; band below 1 MHz unchanged within {abs(10*np.log10(lowB.mean()/lowA.mean())):.1f} dB")
print("\nUL/AE 1-2.5 MHz and total variance at those same B-flagged sweeps vs A stops:")
for c in ('UL','AE'):
    a_=bandpow(A,c)[mA].sum(1).mean(); b_=bandpow(B,c)[eB].sum(1).mean(); print(f"  {c}: total var A {a_:.2e}  B {b_:.2e}  ({10*np.log10(b_/a_):+.2f} dB)")
