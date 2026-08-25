"""M2-lite round 2: dipole + Harris tail + sheath-compressed IMF (+ shock window).
Refit the analytic decomposition with a magnetosheath compression component.
"""
import sys, json, time
import numpy as np
from scipy.optimize import least_squares
sys.path.insert(0, 'surrogate')
from data import load_points

def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))

def dipole(r, mx, mz):
    m = np.array([mx, 0.0, mz])
    r2 = np.einsum('ij,ij->i', r, r)
    mr = r @ m
    return (3 * mr[:, None] * r - m[None, :] * r2[:, None]) / (r2**2.5)[:, None]

def tail(r, B0, L, Bz0, x0, delta):
    z = r[:, 2]
    w = 0.5 * (1 - np.tanh((r[:, 0] - x0) / delta))
    return np.stack([B0 * np.tanh(z / L) * w, np.zeros_like(z), Bz0 * w], axis=1)

def sheath(r, bx, by, bz, R0, Rsh, comp, dmp, dsh, alpha=0.6):
    rn = np.linalg.norm(r, axis=1) + 1e-6
    cos_t = r[:, 0] / rn
    r_mp = R0 * (2.0 / (1.0 + np.cos(np.clip(np.arccos(np.clip(cos_t,-1,1)),0,np.pi))))**0 if False else R0 * (2.0/(1.0+cos_t))**alpha
    r_sh = Rsh * (2.0/(1.0+cos_t))**alpha
    w_mp = sigmoid((rn - r_mp) / dmp)      # 1 outside MP
    w_sh = sigmoid((rn - r_sh) / dsh)      # 1 outside shock
    sw = w_mp * (1.0 - w_sh)               # 1 in the sheath band
    B0v = np.stack([np.full_like(sw, bx), np.full_like(sw, by), np.full_like(sw, bz)], axis=1)
    return B0v * (1.0 + (comp - 1.0) * sw[:, None])

def model(p, r):
    mx, mz, B0, L, Bz0, x0, delta, bx, by, bz, R0, Rsh, comp, dmp, dsh = p
    return dipole(r, mx, mz) + tail(r, B0, L, Bz0, x0, delta) + sheath(r, bx, by, bz, R0, Rsh, comp, dmp, dsh)

def main():
    npz = ['data_swmf/swmf_n600_inner_0.25Re.npz', 'data_swmf/swmf_n600_full_1Re.npz']
    coords, fields = load_points(npz, 100_000, seed=0)
    r = coords
    B_true = np.stack([fields['bx'], fields['by'], fields['bz']], axis=1)
    rng = np.random.default_rng(0)
    perm = rng.permutation(len(r))
    tr, va = perm[:60_000], perm[60_000:]

    p0 = np.array([0.0, -28990.9, 44.7, 0.7, -14.7, 0.0, 6.7, 4.8, -2.2, 0.3, 5.1, 9.0, 3.0, 1.5, 1.5])
    lb = [-5000, -40000, 0, 0.3, -20, -15, 0.5, -20, -20, -20, 3, 6, 1.0, 0.3, 0.3]
    ub = [5000, -5000, 200, 15, 20, 0, 15, 20, 20, 20, 15, 20, 8.0, 6.0, 6.0]

    t0 = time.time()
    res = least_squares(lambda p: (model(p, r[tr]) - B_true[tr]).ravel(),
                        p0, bounds=(lb, ub), x_scale='jac', max_nfev=300, verbose=1)
    print(f'fit done {time.time()-t0:.0f}s nfev={res.nfev} cost={res.cost:.1f}')
    p = res.x
    names = ['mx','mz','B0','L','Bz0','x0','delta','bx','by','bz','R0','Rsh','comp','dmp','dsh']
    print('params:', dict(zip(names, np.round(p, 1))))

    B_pred = model(p, r[va]); Bv = B_true[va]
    bmag_true = np.linalg.norm(Bv, axis=1); bmag_pred = np.linalg.norm(B_pred, axis=1)
    rel = np.abs(bmag_pred - bmag_true) / (bmag_true + 1e-6)
    dot = np.sum(B_pred * Bv, axis=1) / (bmag_pred * bmag_true + 1e-12)
    ang = np.degrees(np.arccos(np.clip(dot, -1, 1)))
    ss_res = np.sum((Bv - B_pred)**2); ss_tot = np.sum((Bv - Bv.mean(0))**2)
    rv = np.linalg.norm(r[va], axis=1)
    def region(mask):
        return dict(rel_med=float(np.median(rel[mask])), ang_med=float(np.median(ang[mask])))
    out = {'r2': float(1 - ss_res/ss_tot), 'params': {k: float(v) for k, v in zip(names, p)},
           'all': region(np.ones_like(rv, bool)),
           'inner_r8': region(rv < 8),
           'tail': region((r[va][:, 0] < -8) & (rv < 30)),
           'sheath': region((r[va][:, 0] > 8) & (rv < 30))}
    print(json.dumps(out, indent=2))
    with open('surrogate/basis2_fit_results.json', 'w') as f:
        json.dump(out, f, indent=2)
    print('FIT2_DONE')

if __name__ == '__main__':
    main()
