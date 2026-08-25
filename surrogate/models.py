"""Three model variants for Phase A."""
import torch
import torch.nn as nn

def fourier_features_torch(x, L=32.0, n_fourier=4):
    """x: [N,3] raw coords -> [N, 3*(1+2*n_fourier)] features, graph-connected."""
    feats = [x / L]
    for k in range(n_fourier):
        s = torch.pi * (2.0 ** k)
        feats += [torch.sin(s * x / L), torch.cos(s * x / L)]
    return torch.cat(feats, dim=1)

class MLP(nn.Module):
    def __init__(self, in_dim, out_dim, hidden=256, layers=6):
        super().__init__()
        seq = [nn.Linear(in_dim, hidden), nn.SiLU()]
        for _ in range(layers - 1):
            seq += [nn.Linear(hidden, hidden), nn.SiLU()]
        seq += [nn.Linear(hidden, out_dim)]
        self.net = nn.Sequential(*seq)

    def forward(self, x):
        return self.net(x)

class DirectB(nn.Module):
    """(a) bare MLP -> B (no physics)."""
    def __init__(self, in_dim):
        super().__init__()
        self.mlp = MLP(in_dim, 3)

    def forward(self, x):
        return self.mlp(x)

class DirectBdivB(nn.Module):
    """(b) bare MLP -> B with soft div-B penalty in loss."""
    def __init__(self, in_dim):
        super().__init__()
        self.mlp = MLP(in_dim, 3)

    def forward(self, x):
        return self.mlp(x)

    def div_b(self, b, x):
        xr = x  # fourier-featurized input; use raw coords instead (see train)
        return None

class AField(nn.Module):
    """(c) MLP -> vector potential A; B = curl(A); Coulomb gauge regularizer."""
    def __init__(self, in_dim):
        super().__init__()
        self.mlp = MLP(in_dim, 3)

    def forward(self, x):
        return self.mlp(x)  # A components

def curl_a(a, xyz):
    """a: [N,3] A components; xyz: [N,3] raw coords (requires_grad). Returns B=[N,3]."""
    Ax, Ay, Az = a[:, 0], a[:, 1], a[:, 2]
    g = lambda v: torch.autograd.grad(v, xyz, grad_outputs=torch.ones_like(v),
                                      create_graph=True, retain_graph=True)[0]
    dAx = g(Ax); dAy = g(Ay); dAz = g(Az)
    bx = dAz[:, 1] - dAy[:, 2]
    by = dAx[:, 2] - dAz[:, 0]
    bz = dAy[:, 0] - dAx[:, 1]
    return torch.stack([bx, by, bz], dim=1)

def div_a(a, xyz):
    Ax, Ay, Az = a[:, 0], a[:, 1], a[:, 2]
    g = lambda v: torch.autograd.grad(v, xyz, grad_outputs=torch.ones_like(v),
                                      create_graph=True, retain_graph=True)[0]
    dAx = g(Ax); dAy = g(Ay); dAz = g(Az)
    return dAx[:, 0] + dAy[:, 1] + dAz[:, 2]

def div_b(b, xyz):
    """div of a directly-predicted B field."""
    bx, by, bz = b[:, 0], b[:, 1], b[:, 2]
    g = lambda v: torch.autograd.grad(v, xyz, grad_outputs=torch.ones_like(v),
                                      create_graph=True, retain_graph=True)[0]
    dbx = g(bx); dby = g(by); dbz = g(bz)
    return dbx[:, 0] + dby[:, 1] + dbz[:, 2]
