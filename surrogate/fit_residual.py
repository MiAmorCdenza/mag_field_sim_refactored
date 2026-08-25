"""M2-lite test: analytic decomposition (dipole+tail+IMF) + MLP on the residual.
Measures whether the NN absorbs the 13% residual better than learning the full field.
"""
import sys, json, time
import numpy as np
import torch
sys.path.insert(0, 'surrogate')
from data import load_points
from models import DirectB, fourier_features_torch

# fitted analytic params (from fit_basis.py)
P = np.array([-2577.73, -28990.86, 44.69, 0.70, -14.71, 0.0, 6.69, 4.78, -2.17, 0.32, 5.11])

def dipole(r, mx, mz):
    m = np.array([mx, 0.0, mz])
    r2 = np.einsum('ij,ij->i', r, r)
    mr = r @ m
    return (3 * mr[:, None] * r - m[None, :] * r2[:, None]) / (r2**2.5)[:, None]

def tail(r, B0, L, Bz0, x0, delta):
    z = r[:, 2]
    w = 0.5 * (1 - np.tanh((r[:, 0] - x0) / delta))
    return np.stack([B0 * np.tanh(z / L) * w, np.zeros_like(z), Bz0 * w], axis=1)

def sw_imf(r, bx, by, bz, R0, alpha=0.6):
    rn = np.linalg.norm(r, axis=1) + 1e-6
    cos_t = r[:, 0] / rn
    r_mp = R0 * (2.0 / (1.0 + cos_t)) ** alpha
    d = np.clip(rn - r_mp, -50, 50)
    w = 1.0 / (1.0 + np.exp(-d / 1.5))
    return np.stack([np.full_like(w, bx), np.full_like(w, by), np.full_like(w, bz)], axis=1) * w[:, None]

def analytic(r):
    mx, mz, B0, L, Bz0, x0, delta, bx, by, bz, R0 = P
    return dipole(r, mx, mz) + tail(r, B0, L, Bz0, x0, delta) + sw_imf(r, bx, by, bz, R0)

def main():
    npz = ['data_swmf/swmf_n600_inner_0.25Re.npz', 'data_swmf/swmf_n600_full_1Re.npz']
    coords, fields = load_points(npz, 160_000, seed=0)
    r = coords
    B_true = np.stack([fields['bx'], fields['by'], fields['bz']], axis=1)
    B_ana = analytic(r)
    B_res = B_true - B_ana
    print('residual share of variance: %.3f' % (np.sum(B_res**2) / np.sum((B_true - B_true.mean(0))**2)))

    rng = np.random.default_rng(0)
    perm = rng.permutation(len(r))
    N_TRAIN = 128_000
    tr, va = perm[:N_TRAIN], perm[N_TRAIN:]
    mu = B_res[tr].mean(0); sd = B_res[tr].std(0)
    b_tr = torch.tensor((B_res[tr] - mu) / sd, dtype=torch.float32)
    xyz_tr = torch.tensor(r[tr], dtype=torch.float32)
    xyz_va = torch.tensor(r[va], dtype=torch.float32)

    torch.manual_seed(0)
    model = DirectB(fourier_features_torch(xyz_tr).shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    BATCH, EPOCHS = 16384, 80
    n_batch = (N_TRAIN + BATCH - 1) // BATCH
    t0 = time.time()
    for ep in range(EPOCHS):
        perm_e = torch.randperm(N_TRAIN)
        tot = 0.0
        for i in range(n_batch):
            idx = perm_e[i*BATCH:(i+1)*BATCH]
            xb = fourier_features_torch(xyz_tr[idx])
            out = model(xb)
            loss = ((out - b_tr[idx]) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item()
        if ep % 10 == 0 or ep == EPOCHS - 1:
            print(f'  [resMLP] ep {ep:3d} loss {tot/n_batch:.4e} ({time.time()-t0:.0f}s)', flush=True)

    with torch.no_grad():
        pred_res = model(fourier_features_torch(xyz_va)).numpy() * sd + mu
    B_pred = B_ana[va] + pred_res
    Bv = B_true[va]
    bmag_true = np.linalg.norm(Bv, axis=1)
    bmag_pred = np.linalg.norm(B_pred, axis=1)
    rel = np.abs(bmag_pred - bmag_true) / (bmag_true + 1e-6)
    dot = np.sum(B_pred * Bv, axis=1) / (bmag_pred * bmag_true + 1e-12)
    ang = np.degrees(np.arccos(np.clip(dot, -1, 1)))
    rv = np.linalg.norm(r[va], axis=1)
    def region(mask):
        return dict(rel_med=float(np.median(rel[mask])), ang_med=float(np.median(ang[mask])))
    out = {
        'combined': region(np.ones_like(rv, bool)),
        'inner_r8': region(rv < 8),
        'tail': region((r[va][:, 0] < -8) & (rv < 30)),
        'sheath': region((r[va][:, 0] > 8) & (rv < 30)),
        'analytic_only': dict(
            rel_med=float(np.median(np.abs(np.linalg.norm(B_ana[va],axis=1)-bmag_true)/(bmag_true+1e-6))),
        ),
    }
    print(json.dumps(out, indent=2))
    torch.save(model.state_dict(), 'surrogate/ckpt_resMLP.pt')
    print('RESIDUAL_MLP_DONE')

if __name__ == '__main__':
    main()
