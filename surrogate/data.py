"""Load SWMF npz grids, build point-cloud datasets with Fourier features."""
import numpy as np
import torch

R_MIN = 3.0        # exclude inner-boundary spike (body at 2.5 Re)
R_MAX = 60.0       # outer cutoff for training
N_FOURIER = 4      # octaves of Fourier features
L_FOURIER = 32.0   # base wavelength scale [Re]

def load_points(npz_paths, n_points=None, seed=0):
    """Load npz grid(s) -> (coords [N,3], fields dict of [N,..]) masked by radius."""
    rng = np.random.default_rng(seed)
    xs, fs = [], []
    for p in npz_paths:
        d = np.load(p)
        X, Y, Z = np.meshgrid(d['x'], d['y'], d['z'], indexing='ij')
        r = np.sqrt(X**2 + Y**2 + Z**2)
        m = (r >= R_MIN) & (r <= R_MAX)
        xs.append(np.column_stack([X[m], Y[m], Z[m]]))
        fs.append({k: d[k][m] for k in ['rho', 'ux', 'uy', 'uz', 'bx', 'by', 'bz', 'p', 'ex', 'ey', 'ez']})
    coords = np.concatenate(xs)
    fields = {k: np.concatenate([f[k] for f in fs]) for k in fs[0]}
    if n_points and len(coords) > n_points:
        idx = rng.choice(len(coords), n_points, replace=False)
        coords, fields = coords[idx], {k: v[idx] for k, v in fields.items()}
    return coords, fields

def fourier_features(x):
    """x: [N,3] in Re -> [N, 3*(1+2*N_FOURIER)] raw + sin/cos encodings."""
    feats = [x / L_FOURIER]
    for k in range(N_FOURIER):
        s = np.pi * (2.0 ** k)
        feats += [np.sin(s * x / L_FOURIER), np.cos(s * x / L_FOURIER)]
    return np.concatenate(feats, axis=1)

def make_tensors(coords, fields, n_train, seed=0):
    """Split point cloud into train/val tensors with target normalization stats."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(coords))
    tr, va = perm[:n_train], perm[n_train:]
    x_tr = torch.tensor(fourier_features(coords[tr]), dtype=torch.float32)
    x_va = torch.tensor(fourier_features(coords[va]), dtype=torch.float32)
    b_tr_raw = np.stack([fields['bx'][tr], fields['by'][tr], fields['bz'][tr]], axis=1)
    b_va_raw = np.stack([fields['bx'][va], fields['by'][va], fields['bz'][va]], axis=1)
    mu = b_tr_raw.mean(axis=0); sd = b_tr_raw.std(axis=0)
    b_tr = torch.tensor((b_tr_raw - mu) / sd, dtype=torch.float32)
    b_va = torch.tensor((b_va_raw - mu) / sd, dtype=torch.float32)
    stats = {'mu': mu, 'sd': sd, 'n_train': n_train, 'n_val': len(va)}
    return x_tr, b_tr, x_va, b_va, stats
