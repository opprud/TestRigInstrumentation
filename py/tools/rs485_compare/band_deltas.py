from common import *
A=load('A_manual.npz'); B=load('B_modbus.npz')
def prep(d):
    t,rb,sv,st=cells(d); return dict(rb=rb,sv=sv,st=st,bp={c:bandpow(d,c) for c in CH})
a,b=prep(A),prep(B)
LV=[40,55,70,85,100]
def table(c):
    print(f"\n=== {c}: delta dB = B(RS485 on) - A(RS485 off), settled sweeps, mean over temperature levels (n levels); * = |mean|>2SE and >1 dB ===")
    print('band'.ljust(11)+''.join(f'{r:>13}' for r in RPMBINS))
    for j,bd in enumerate(BANDS):
        row=bname(bd).ljust(11)
        for r in RPMBINS:
            ds=[]
            for L in LV:
                ma=(a['rb']==r)&(a['sv']==L)&a['st']; mb=(b['rb']==r)&(b['sv']==L)&b['st']
                if ma.sum()>=2 and mb.sum()>=2:
                    ds.append(10*np.log10(np.median(b['bp'][c][mb,j])/np.median(a['bp'][c][ma,j])))
            if len(ds)>=2:
                m=np.mean(ds); se=np.std(ds,ddof=1)/np.sqrt(len(ds)); star='*' if abs(m)>2*se and abs(m)>1 else ' '
                row+=f"{m:+7.1f}{star}({len(ds)})  "
            else: row+=' '*13
        print(row)
for c in CH: table(c)
