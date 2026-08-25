#!/usr/bin/env python3
"""Extract SWMF 3D Tecplot (16-col: I x y z rho ux uy uz bx by bz p jx jy jz)
-> uniform-grid npz with rho,u,B,p,j and E=-uxB. Uses cKDTree nearest."""
import sys, os, re, argparse
import numpy as np
from scipy.spatial import cKDTree

def load_tec(path):
    rows = []
    in_data = False
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith('ZONE'):
                in_data = True
                continue
            if line.startswith(('TITLE', 'VARIABLES', 'AUXDATA', 'DATASET')):
                continue
            if in_data:
                try:
                    rows.append([float(v) for v in line.split()])
                except ValueError:
                    break
    return np.array(rows, dtype=np.float64)

def resample(d, x0, x1, y0, y1, z0, z1, nx, ny, nz):
    # d cols: I x y z rho ux uy uz bx by bz p jx jy jz
    x, y, z = d[:, 1], d[:, 2], d[:, 3]
    m = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (z >= z0) & (z <= z1)
    d = d[m]
    if len(d) < 1000:
        return None
    tree = cKDTree(d[:, 1:4])
    xt = np.linspace(x0, x1, nx); yt = np.linspace(y0, y1, ny); zt = np.linspace(z0, z1, nz)
    X, Y, Z = np.meshgrid(xt, yt, zt, indexing='ij')
    pts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    _, idx = tree.query(pts, k=1)
    out = d[idx, 4:].reshape(nx, ny, nz, -1)   # rho ux uy uz bx by bz p jx jy jz
    return xt, yt, zt, out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tec_file')
    ap.add_argument('out_dir')
    ap.add_argument('--tag', default='swmf')
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    d = load_tec(args.tec_file)
    print('loaded %d points' % len(d))
    grids = [(-90.0, 25.0, -45.0, 45.0, -45.0, 45.0, 116, 91, 91, 'full_1Re'),
             (-20.0, 10.0, -12.0, 12.0, -12.0, 12.0, 121, 97, 97, 'inner_0.25Re')]
    for (x0, x1, y0, y1, z0, z1, nx, ny, nz, tag) in grids:
        r = resample(d, x0, x1, y0, y1, z0, z1, nx, ny, nz)
        if r is None:
            print('  %s: too few points, skip' % tag); continue
        xt, yt, zt, f = r
        rho, ux, uy, uz, bx, by, bz, p, jx, jy, jz = [f[..., k] for k in range(11)]
        ex = -(uy * bz - uz * by) * 1e-6
        ey = -(uz * bx - ux * bz) * 1e-6
        ez = -(ux * by - uy * bx) * 1e-6
        fname = os.path.join(args.out_dir, '%s_%s.npz' % (args.tag, tag))
        np.savez_compressed(fname, x=xt, y=yt, z=zt,
                            rho=rho, ux=ux, uy=uy, uz=uz,
                            bx=bx, by=by, bz=bz, p=p,
                            jx=jx, jy=jy, jz=jz,
                            ex=ex, ey=ey, ez=ez)
        print('  -> %s (%.1f MB)' % (fname, os.path.getsize(fname)/1e6))

if __name__ == '__main__':
    main()
