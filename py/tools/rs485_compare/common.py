import numpy as np
CH=('UL','AE','SP')
BANDS=[(0,500),(500,1500),(1500,3000),(3000,6000),(6000,10000),(1e4,2e4),(2e4,5e4),(5e4,1e5),(1e5,2e5),(2e5,5e5),(5e5,1e6),(1e6,2.5e6)]
def bname(b):
    f=lambda x:f"{x/1e3:g}k" if x>=1e3 else f"{x:g}"
    return f"{f(b[0])}-{f(b[1])}"
RPMBINS={0:(-1,20),600:(540,640),1200:(1130,1260),1800:(1740,1860),2400:(2330,2450),3000:(2900,3100)}
def load(p):
    z=np.load(p); d={k:z[k] for k in z.files}; return d
def rpmbin(r):
    out=np.full(len(r),-1)
    for b,(lo,hi) in RPMBINS.items(): out[(r>lo)&(r<=hi)]=b
    return out
def bandpow(d,c):
    f=d['freq']; P=d[f'{c}_psd'].astype(np.float64); df=f[1]-f[0]
    return np.stack([P[:,(f>=lo)&(f<hi)].sum(1)*df for lo,hi in BANDS],1)   # V^2 per band
def cells(d):
    t=dict(zip(d['tel_names'],d['tel'].T))
    rb=rpmbin(t['telem_rpm_meas']); sv=t['telem_temp_target']; settled=np.abs(t['telem_omron_pv_c']-sv)<=5
    return t,rb,sv,settled
