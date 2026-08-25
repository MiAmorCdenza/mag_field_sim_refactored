"""Phase A: pipeline validation on one SWMF snapshot. Three variants:
(a) bare MLP -> B   (b) MLP -> B + soft div-B penalty   (c) MLP -> A, B=curl(A) + Coulomb gauge.
Metrics: relative |B| error, angular error, |div B|/|B| in regions.
"""
import json, os, sys, time
import numpy as np
import torch

from data import load_points, make_tensors, fourier_features
from models import DirectB, DirectBdivB, AField, curl_a, div_a, div_b, fourier_features_torch

N_POINTS = 200_000
N_TRAIN = 160_000
BATCH = 16384
EPOCHS = 40
LR = 1e-3
SEED = 0

def run_variant(name, npz_paths, n_points=None, n_train=None, epochs=None):
    n_points = n_points or N_POINTS
    n_train = n_train or N_TRAIN
    epochs = epochs or EPOCHS
    torch.manual_seed(SEED)
    coords, fields = load_points(npz_paths, n_points, seed=SEED)
    _, _, _, _, stats = make_tensors(coords, fields, n_train, seed=SEED)
    rng = np.random.default_rng(SEED)
    perm = rng.permutation(len(coords)); tr, va = perm[:n_train], perm[n_train:]
    xyz_tr = torch.tensor(coords[tr], dtype=torch.float32, requires_grad=True)
    xyz_va = torch.tensor(coords[va], dtype=torch.float32, requires_grad=True)
    r_va = np.linalg.norm(coords[va], axis=1)
    b_tr_raw = np.stack([fields['bx'][tr], fields['by'][tr], fields['bz'][tr]], axis=1)
    b_va_raw = np.stack([fields['bx'][va], fields['by'][va], fields['bz'][va]], axis=1)
    mu, sd = stats['mu'], stats['sd']
    b_tr = torch.tensor((b_tr_raw - mu) / sd, dtype=torch.float32)
    xyz_tr = xyz_tr.requires_grad_(True)

    in_dim = fourier_features_torch(xyz_tr).shape[1]
    if name == 'a_mlp_B':
        model, use_a, lam_gauge, lam_div = DirectB(in_dim), False, 0.0, 0.0
    elif name == 'b_mlp_B_divpen':
        model, use_a, lam_gauge, lam_div = DirectBdivB(in_dim), False, 0.0, 0.1
    else:
        model, use_a, lam_gauge, lam_div = AField(in_dim), True, 0.01, 0.0

    opt = torch.optim.Adam(model.parameters(), lr=LR)
    n_batch = (n_train + BATCH - 1) // BATCH
    t0 = time.time()
    for ep in range(epochs):
        model.train()
        perm_e = torch.randperm(n_train)
        tot = 0.0
        for i in range(n_batch):
            idx = perm_e[i * BATCH:(i + 1) * BATCH]
            xz = xyz_tr[idx].detach().requires_grad_(True)
            xb = fourier_features_torch(xz)
            bb = b_tr[idx]
            out = model(xb)
            if use_a:
                b_pred = curl_a(out, xz)
                loss = ((b_pred - bb) ** 2).mean()
                if lam_gauge > 0:
                    loss = loss + lam_gauge * (div_a(out, xz) ** 2).mean()
            else:
                b_pred = out
                loss = ((b_pred - bb) ** 2).mean()
                if lam_div > 0:
                    loss = loss + lam_div * (div_b(b_pred, xz) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item()
        if ep % 10 == 0 or ep == epochs - 1:
            print(f'  [{name}] ep {ep:3d} loss {tot/n_batch:.4e}  ({time.time()-t0:.0f}s)', flush=True)

    # ---- evaluation on validation points ----
    model.eval()
    xv = xyz_va.requires_grad_(True)
    out = model(fourier_features_torch(xv))
    if use_a:
        b_pred = curl_a(out, xv)
    else:
        b_pred = out
    b_pred_np = (b_pred.detach().numpy() * sd[None, :]) + mu[None, :]
    bmag_true = np.linalg.norm(b_va_raw, axis=1)
    bmag_pred = np.linalg.norm(b_pred_np, axis=1)
    rel = np.abs(bmag_pred - bmag_true) / (bmag_true + 1e-6)
    dot = np.sum(b_pred_np * b_va_raw, axis=1) / (bmag_pred * bmag_true + 1e-12)
    ang = np.degrees(np.arccos(np.clip(dot, -1, 1)))
    if not use_a:
        div = div_b(b_pred, xv).detach().numpy()
    else:
        div = np.zeros_like(bmag_true)  # div B == 0 by construction
    divnorm = np.abs(div) / (bmag_true + 1e-6)

    def region(mask):
        return dict(rel_med=float(np.median(rel[mask])), rel_p90=float(np.percentile(rel[mask], 90)),
                    ang_med=float(np.median(ang[mask])), div_med=float(np.median(divnorm[mask])))

    res = {
        'variant': name,
        'n_train': n_train, 'n_val': len(va), 'epochs': epochs,
        'all': region(np.ones_like(r_va, bool)),
        'inner_r8': region(r_va < 8),
        'tail': region((coords[va][:, 0] < -8) & (r_va < 30)),
        'sheath': region((coords[va][:, 0] > 8) & (r_va < 30)),
    }
    torch.save(model.state_dict(), f'surrogate/ckpt_{name}.pt')
    print(f'  [{name}] results: {json.dumps(res, ensure_ascii=False)}', flush=True)
    return res

if __name__ == '__main__':
    npz = ['data_swmf/swmf_n600_inner_0.25Re.npz', 'data_swmf/swmf_n600_full_1Re.npz']
    names = sys.argv[1:] or ['a_mlp_B', 'b_mlp_B_divpen', 'c_mlp_A']
    results = []
    for name in names:
        results.append(run_variant(name, npz))
    with open('surrogate/phaseA_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print('\n=== PHASE A SUMMARY ===')
    for r in results:
        print(f"{r['variant']:20s} all: rel_med={r['all']['rel_med']:.3f} ang_med={r['all']['ang_med']:.1f}deg  "
              f"inner: rel_med={r['inner_r8']['rel_med']:.3f} ang_med={r['inner_r8']['ang_med']:.1f}deg  "
              f"tail: rel_med={r['tail']['rel_med']:.3f}  sheath: rel_med={r['sheath']['rel_med']:.3f}")
