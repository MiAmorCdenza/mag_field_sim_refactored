"""Physical-decomposition baseline: fit dipole + Harris tail + MP-windowed IMF
to the SWMF n600 snapshot. Measures the analytic components' explained variance
and the residual share -> informs the M2 route (physics decomposition + NN residual).
"""
import sys, json, time
import numpy as np
from scipy.optimize import least_squares
sys.path.insert(0, 'surrogate')
from data import load_points

R_MIN, R_MAX = 3.0, 60.0

def dipole(r, mx, mz):
    m = np.array([mx, 0.0, mz])
    r2 = np.einsum('ij,ij->i', r, r)
    mr = r @ m
    B = (3 * mr[:, None] * r - m[None, :] * r2[:, None]) / (r2**2.5)[:, None]
    return B

def tail(r, B0, L, Bz0, x0, delta):
    z = r[:, 2]
    w = 0.5 * (1 - np.tanh((r[:, 0] - x0) / delta))
    Bx = B0 * np.tanh(z / L) * w
    Bz = Bz0 * w
    return np.stack([Bx, np.zeros_like(z), Bz], axis=1)

def sw_imf(r, bx, by, bz, R0, alpha=0.6):
    rn = np.linalg.norm(r, axis=1) + 1e-6
    cos_t = r[:, 0] / rn
    r_mp = R0 * (2.0 / (1.0 + cos_t)) ** alpha
    d = rn - r_mp
    w = 1.0 / (1.0 + np.exp(-d / 1.5))
    return np.stack([np.full_like(w, bx), np.full_like(w, by), np.full_like(w, bz)], axis=1) * w[:, None]

def model(p, r):
    mx, mz, B0, L, Bz0, x0, delta, bx, by, bz, R0 = p
    return dipole(r, mx, mz) + tail(r, B0, L, Bz0, x0, delta) + sw_imf(r, bx, by, bz, R0)

def main():
    npz = ['data_swmf/swmf_n600_inner_0.25Re.npz', 'data_swmf/swmf_n600_full_1Re.npz']
    coords, fields = load_points(npz, 100_000, seed=0)
    r = coords
    B_true = np.stack([fields['bx'], fields['by'], fields['bz']], axis=1)

    # train/val split by random points
    rng = np.random.default_rng(0)
    perm = rng.permutation(len(r))
    tr, va = perm[:60_000], perm[60_000:]

    p0 = np.array([0.0, -25600.0, 56.0, 3.0, -2.5, -2.0, 3.0, 3.2, -1.1, -4.8, 6.0])
    lb = [-5000, -40000, 0, 0.3, -20, -15, 0.5, -20, -20, -20, 3]
    ub = [5000, -5000, 200, 15, 20, 0, 15, 20, 20, 20, 15]

    t0 = time.time()
    res = least_squares(lambda p: (model(p, r[tr]) - B_true[tr]).ravel(),
                        p0, bounds=(lb, ub), x_scale='jac', max_nfev=200, verbose=1)
    print(f'fit done in {time.time()-t0:.0f}s, cost={res.cost:.2f}, nfev={res.nfev}')
    p = res.x
    print('params:', dict(zip(['mx','mz','B0','L','Bz0','x0','delta','bx','by','bz','R0'], np.round(p,1))))

    B_pred = model(p, r[va])
    Bv = B_true[va]
    bmag_true = np.linalg.norm(Bv, axis=1)
    bmag_pred = np.linalg.norm(B_pred, axis=1)
    rel = np.abs(bmag_pred - bmag_true) / (bmag_true + 1e-6)
    dot = np.sum(B_pred * Bv, axis=1) / (bmag_pred * bmag_true + 1e-12)
    ang = np.degrees(np.arccos(np.clip(dot, -1, 1)))

    # explained variance (R2) over the val set
    ss_res = np.sum((Bv - B_pred) ** 2)
    ss_tot = np.sum((Bv - Bv.mean(0)) ** 2)
    r2 = 1 - ss_res / ss_tot

    def region(mask):
        return dict(rel_med=float(np.median(rel[mask])), ang_med=float(np.median(ang[mask])))
    rv = np.linalg.norm(r[va], axis=1)
    out = {
        'r2': float(r2),
        'resid_frac': float(ss_res / ss_tot),
        'params': {k: float(v) for k, v in zip(['mx','mz','B0','L','Bz0','x0','delta','bx','by','bz','R0'], p)},
        'all': region(np.ones_like(rv, bool)),
        'inner_r8': region(rv < 8),
        'tail': region((r[va][:, 0] < -8) & (rv < 30)),
        'sheath': region((r[va][:, 0] > 8) & (rv < 30)),
    }
    print(json.dumps(out, indent=2))
    with open('surrogate/basis_fit_results.json', 'w') as f:
        json.dump(out, f, indent=2)
    print('FIT_BASIS_DONE')

if __name__ == '__main__':
    main()
