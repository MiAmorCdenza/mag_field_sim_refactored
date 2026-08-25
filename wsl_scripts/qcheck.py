#!/usr/bin/env python3
"""Numerical QC of extracted SWMF grid: verify magnetosphere structure formed."""
import sys, numpy as np

f = sys.argv[1]
d = np.load(f)
print("file:", f)
print("x range:", d['x'][0], d['x'][-1], " n=", len(d['x']))
print("shape:", d['bx'].shape)

x, y, z = d['x'], d['y'], d['z']
bx, by, bz = d['bx'], d['by'], d['bz']
rho, ux = d['rho'], d['ux']
ex, ey, ez = d['ex'], d['ey'], d['ez']
Bmag = np.sqrt(bx**2 + by**2 + bz**2)

def at(px, py, pz):
    i = np.argmin(np.abs(x - px)); j = np.argmin(np.abs(y - py)); k = np.argmin(np.abs(z - pz))
    return i, j, k

print("\n--- QC diagnostics ---")
# 1) near-Earth field strength (should be >> 100 nT)
i, j, k = at(3.0, 0, 0)
print(f"[1] |B| at (3,0,0) = {Bmag[i,j,k]:.0f} nT  (dipole+ring current region, expect >300)")
# 2) subsolar magnetopause: |B| transition along +x axis
print("[2] |B| along +x axis (z=y=0):")
for px in [5, 7, 9, 10, 12, 15]:
    i, j, k = at(px, 0, 0)
    print(f"    x={px:>3} Re: |B|={Bmag[i,j,k]:8.1f} nT, rho={rho[i,j,k]:6.2f}, ux={ux[i,j,k]:7.1f}")
# 3) bow shock: density jump upstream
i1 = at(20, 0, 0); i2 = at(5, 0, 0)
print(f"[3] rho(20,0,0)={rho[i1]:.2f} vs rho(5,0,0)={rho[i2]:.2f} (sheath compression if ratio>1.5)")
# 4) tail lobe Bx sign reversal
i, j, k1 = at(-30, 0, 8); i, j, k2 = at(-30, 0, -8)
print(f"[4] tail lobes x=-30: Bx(z=+8)={bx[i,j,k1]:+7.2f} nT, Bx(z=-8)={bx[i,j,k2]:+7.2f} nT (expect opposite signs)")
# 5) plasma sheet Bx ~ 0
i, j, k = at(-30, 0, 0)
print(f"[5] neutral sheet x=-30,z=0: |B|={Bmag[i,j,k]:.2f} nT (expect small), Bz={bz[i,j,k]:+.2f}")
# 6) upstream Ey (convection) sign: southward IMF -> Ey > 0 (duskward)
i, j, k = at(15, 0, 0)
print(f"[6] upstream E at (15,0,0): ({ex[i,j,k]:+.2e}, {ey[i,j,k]:+.2e}, {ez[i,j,k]:+.2e}) V/m (expect Ey>0 for Bz<0)")
# 7) E=-uxB self-consistency residual
E_cross = np.stack([ex, ey, ez], axis=-1)
u = np.stack([ux, d['uy'], d['uz']], axis=-1)
B = np.stack([bx, by, bz], axis=-1)
E_recon = -np.cross(u, B) * 1e-6
resid = np.linalg.norm(E_cross - E_recon, axis=-1)
print(f"[7] E vs -uxB residual: mean={resid.mean():.2e} V/m (should be ~0)")
# 8) min/max field
print(f"[8] |B| range: {Bmag.min():.1f} .. {Bmag.max():.1f} nT")
