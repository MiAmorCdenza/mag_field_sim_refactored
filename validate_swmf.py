#!/usr/bin/env python3
"""Compare SWMF 90Re z=0 Tecplot output with our model."""
import numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import python_bridge as pb

# Read SWMF Tecplot
tec = r'Z:\SWMF\run_test_90Re\GM\IO2\z=0_ful_3_n00000020.tec'
with open(tec) as f:
    lines = f.readlines()

# Find data start
ds = 0
for i, l in enumerate(lines):
    if l.strip().startswith('ZONE'):
        ds = i + 1
        while ds < len(lines) and (lines[ds].strip().startswith('AUX') or not lines[ds].strip()):
            ds += 1
        break

data = np.loadtxt(lines[ds:], dtype=np.float32)
n = len(data)
x_s = data[:, 0].astype(np.float64)
y_s = data[:, 1].astype(np.float64)
bx_s = data[:, 8].astype(np.float64)
by_s = data[:, 9].astype(np.float64)
bz_s = data[:, 10].astype(np.float64)

print(f"SWMF 90Re z=0: {n} points")
print(f"  X=[{x_s.min():.1f}, {x_s.max():.1f}] Re")
print(f"  Y=[{y_s.min():.1f}, {y_s.max():.1f}] Re")
print(f"  Bx [{bx_s.min():.2f}, {bx_s.max():.2f}] nT")
print(f"  By [{by_s.min():.2f}, {by_s.max():.2f}] nT")
print(f"  Bz [{bz_s.min():.2f}, {bz_s.max():.2f}] nT")

# Diagnostic points
pts = [
    (12.0, 0.0, "Subsolar nose"),
    (10.0, 5.0, "Dayside mid"),
    (8.0, 8.0, "Near MP flank"),
    (5.0, 10.0, "Flank mid"),
    (0.0, 12.0, "Terminator dusk"),
    (-5.0, 10.0, "Near-tail flank"),
    (-10.0, 5.0, "Near-tail mid"),
    (-15.0, 0.0, "Mid-tail axis"),
    (-30.0, 0.0, "Far-tail axis"),
    (-30.0, 10.0, "Far-tail flank"),
    (-60.0, 0.0, "Deep tail"),
    (-80.0, 15.0, "Far flank"),
]

xp = np.array([p[0] for p in pts], dtype=np.float64)
yp = np.array([p[1] for p in pts], dtype=np.float64)
zp = np.zeros(len(pts))

kp, ps = 2.0, 0.0
pb._parker_custom = True
pb._parker_angle_deg = 40.0

bx_e, by_e, bz_e = pb._compute_external(4, kp, ps, xp, yp, zp)
bx_d, by_d, bz_d = pb._compute_dipole(ps, xp, yp, zp)
bx_o, by_o, bz_o = pb._apply_magnetopause_envelope(
    np.array(bx_e), np.array(by_e), np.array(bz_e),
    xp, yp, zp, tail_model=2, magnetopause_model=2, kp=kp, ps=ps,
    bx_dipole=np.array(bx_d), by_dipole=np.array(by_d), bz_dipole=np.array(bz_d))

print()
print(f"{'Point':<22s} {'Model':>6s} {'Bx':>9s} {'By':>9s} {'Bz':>9s} {'|B|':>9s} {'d':>5s}")
print('-' * 75)
diffs = []
for i, (px, py, label) in enumerate(pts):
    idx = np.argmin((x_s-px)**2 + (y_s-py)**2)
    sbx, sby, sbz = bx_s[idx], by_s[idx], bz_s[idx]
    sb = np.sqrt(sbx**2 + sby**2 + sbz**2)
    ob = np.sqrt(bx_o[i]**2 + by_o[i]**2 + bz_o[i]**2)
    db = np.sqrt((bx_o[i]-sbx)**2 + (by_o[i]-sby)**2 + (bz_o[i]-sbz)**2)
    diffs.append(db)
    flag = 'OK' if db < max(8, 0.5*sb) else (' ~' if db < 15 else ' !!')
    print(f'{label:<22s} {"SWMF":>6s} {sbx:9.2f} {sby:9.2f} {sbz:9.2f} {sb:9.2f}')
    print(f'{"":22s} {"Ours":>6s} {bx_o[i]:9.2f} {by_o[i]:9.2f} {bz_o[i]:9.2f} {ob:9.2f} {flag:>5s}')

print()
print('=' * 75)
print(f'Mean |delta B|: {np.mean(diffs):.2f} nT')
print(f'Max  |delta B|: {np.max(diffs):.2f} nT')
print(f'Sample size: {len(diffs)} points')
