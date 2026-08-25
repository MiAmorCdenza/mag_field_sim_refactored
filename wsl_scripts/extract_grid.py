#!/usr/bin/env python3
"""Extract SWMF 3D tec snapshots -> uniform-grid npz with rho, u, B, p, E=-uxB.

Usage: python3 extract_grid.py <io2_dir> <out_dir> [--times t1,t2,...]
"""
import sys, os, re, glob, argparse
import numpy as np
from scipy.spatial import cKDTree

def discover_snapshots(io2_dir):
    snaps = []
    for fpath in sorted(glob.glob(os.path.join(io2_dir, '3d__var_1_t*_1.tec'))):
        base = os.path.basename(fpath)
        m = re.match(r'3d__var_1_t(\d{8})_n(\d{8})_1\.tec', base)
        if not m:
            continue
        prefix = '3d__var_1_t' + m.group(1) + '_n' + m.group(2)
        hdr = os.path.join(io2_dir, prefix + '_0.tec')
        dat = os.path.join(io2_dir, prefix + '_1.tec')
        if not (os.path.exists(hdr) and os.path.exists(dat)):
            continue
        t = 0.0
        th = os.path.join(io2_dir, prefix + '.T')
        if os.path.exists(th):
            for line in open(th):
                tm = re.match(r'\s*([\d.]+(?:E[+-]?\d+)?)\s+t\s*', line, re.I)
                if tm:
                    t = float(tm.group(1)); break
        snaps.append({'sim_time': t, 'step': int(m.group(2)), 'hdr': hdr, 'dat': dat})
    snaps.sort(key=lambda s: s['sim_time'])
    return snaps

def load_snapshot(hdr, dat):
    """Merge header+data tec, parse into point cloud. Columns: x y z rho ux uy uz bx by bz p."""
    rows = []
    in_data = False
    for f in (hdr, dat):
        for line in open(f):
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
    """Nearest-neighbour resample of the AMR point cloud onto a uniform grid."""
    x, y, z = d[:, 0], d[:, 1], d[:, 2]
    m = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (z >= z0) & (z <= z1)
    d = d[m]
    if len(d) < 1000:
        return None
    tree = cKDTree(d[:, :3])
    xt = np.linspace(x0, x1, nx)
    yt = np.linspace(y0, y1, ny)
    zt = np.linspace(z0, z1, nz)
    X, Y, Z = np.meshgrid(xt, yt, zt, indexing='ij')
    pts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    _, idx = tree.query(pts, k=1)
    out = d[idx, 3:].reshape(nx, ny, nz, -1)  # rho ux uy uz bx by bz p
    return xt, yt, zt, out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('io2_dir')
    ap.add_argument('out_dir')
    ap.add_argument('--times', default=None)
    ap.add_argument('--max', type=int, default=8)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    snaps = discover_snapshots(args.io2_dir)
    print('found %d snapshots' % len(snaps))
    if not snaps:
        print('NO SNAPSHOTS YET'); return
    if args.times:
        targets = [float(t) for t in args.times.split(',')]
        snaps = [min(snaps, key=lambda s: abs(s['sim_time'] - t)) for t in targets]
    else:
        snaps = snaps[-args.max:]
    grids = [(-90.0, 25.0, -45.0, 45.0, -45.0, 45.0, 116, 91, 91, 'full_1Re'),
             (-20.0, 10.0, -12.0, 12.0, -12.0, 12.0, 121, 97, 97, 'inner_0.25Re')]
    for s in snaps:
        d = load_snapshot(s['hdr'], s['dat'])
        print('t=%.0fs step=%d points=%d' % (s['sim_time'], s['step'], len(d)))
        for (x0, x1, y0, y1, z0, z1, nx, ny, nz, tag) in grids:
            r = resample(d, x0, x1, y0, y1, z0, z1, nx, ny, nz)
            if r is None:
                print('  %s: too few points, skip' % tag); continue
            xt, yt, zt, f = r
            rho, ux, uy, uz, bx, by, bz, p = [f[..., k] for k in range(8)]
            ex = -(uy * bz - uz * by) * 1e-6
            ey = -(uz * bx - ux * bz) * 1e-6
            ez = -(ux * by - uy * bx) * 1e-6
            fname = os.path.join(args.out_dir, 'swmf_t%08.0f_%s.npz' % (s['sim_time'], tag))
            np.savez_compressed(fname, x=xt, y=yt, z=zt,
                                rho=rho, ux=ux, uy=uy, uz=uz,
                                bx=bx, by=by, bz=bz, p=p,
                                ex=ex, ey=ey, ez=ez)
            print('  -> %s (%.1f MB)' % (fname, os.path.getsize(fname)/1e6))

if __name__ == '__main__':
    main()
