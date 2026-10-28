"""Per-sweep features for one run -> npz.  usage: extract.py <run_id> <out.npz>"""
import sys, glob, numpy as np, h5py
from scipy import signal
from multiprocessing import Pool
RUN, OUT = sys.argv[1], sys.argv[2]
PATH = glob.glob(f'/home/aau/projects/ForeverBearing/sw/TestRigInstrumentation/py/data/runs/{RUN}/*.h5')[0]
CH = ('UL', 'AE', 'SP'); FS = 5e6; NPS = 65536
FB = {'b2_8k': (2e3, 8e3), 'b10_50k': (1e4, 5e4)}      # frame-energy bands (1 ms frames)
TEL = ['tick','telem_rpm_meas','telem_rpm_target','telem_omron_pv_c','telem_omron_sv_c','telem_temp_target','telem_vfd_cmd_hz']

def one(k):
    with h5py.File(PATH, 'r') as h:
        g = h['sweeps'][k]
        tel = [float(g.attrs.get(a, np.nan)) for a in TEL]
        rows = {}
        for c in CH:
            v = g[c]['voltage'][:].astype(np.float64)
            f, p = signal.welch(v, FS, window='hann', nperseg=NPS, detrend='constant')
            fr, ft, S = signal.spectrogram(v, FS, window='hann', nperseg=5000, noverlap=0, detrend='constant', mode='psd')
            fe = {n: S[(fr >= lo) & (fr < hi)].sum(0) for n, (lo, hi) in FB.items()}
            rows[c] = dict(mean=v.mean(), rms=v.std(), vpp=np.ptp(v), psd=p.astype(np.float32), fe=fe)
    return k, tel, rows

if __name__ == '__main__':
    with h5py.File(PATH, 'r') as h: keys = sorted(h['sweeps'])
    with Pool(2) as pool: res = pool.map(one, keys, chunksize=4)
    out = dict(keys=np.array([r[0] for r in res]), tel=np.array([r[1] for r in res]), tel_names=np.array(TEL), freq=np.fft.rfftfreq(NPS, 1/FS)[:NPS//2+1])
    for c in CH:
        out[f'{c}_mean'] = np.array([r[2][c]['mean'] for r in res]); out[f'{c}_rms'] = np.array([r[2][c]['rms'] for r in res])
        out[f'{c}_vpp'] = np.array([r[2][c]['vpp'] for r in res]); out[f'{c}_psd'] = np.stack([r[2][c]['psd'] for r in res])
        for n in FB: out[f'{c}_fe_{n}'] = np.stack([r[2][c]['fe'][n] for r in res])
    np.savez_compressed(OUT, **out); print('done', RUN, len(res))
