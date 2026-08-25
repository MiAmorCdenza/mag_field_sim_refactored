"""Verify IGRF + T04 combination works correctly."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import python_bridge
import numpy as np
import geopack

# Re-init IGRF
geopack.recalc(43200)

# Test point: near-Earth equator at 1.05 Re
x, y, z = 1.05, 0.0, 0.0

# IGRF only
bx_i, by_i, bz_i = geopack.igrf_gsm(x, y, z)
bmag_i = np.sqrt(bx_i**2 + by_i**2 + bz_i**2)
print(f"IGRF  at (1.05,0,0): B=({bx_i:.0f}, {by_i:.0f}, {bz_i:.0f}) nT, |B|={bmag_i:.0f} nT")

# T04 external only
bx_e, by_e, bz_e = python_bridge._compute_external(4, 2.0, 0.0, np.array([x]), np.array([y]), np.array([z]))
print(f"T04   at (1.05,0,0): B=({bx_e[0]:.0f}, {by_e[0]:.0f}, {bz_e[0]:.0f}) nT")

# Total
bx_t, by_t, bz_t = bx_i + bx_e[0], by_i + by_e[0], bz_i + bz_e[0]
bmag_t = np.sqrt(bx_t**2 + by_t**2 + bz_t**2)
print(f"Total at (1.05,0,0): B=({bx_t:.0f}, {by_t:.0f}, {bz_t:.0f}) nT, |B|={bmag_t:.0f} nT")

# Test through compute_grid
print("\nTesting compute_grid with moderate resolution...")
bx, by, bz = python_bridge.compute_grid(4, 2.0, 0.0, -5.0, 5.0, 21, -5.0, 5.0, 21, -5.0, 5.0, 21)
bx_a, by_a, bz_a = np.array(bx), np.array(by), np.array(bz)
Xf = np.linspace(-5, 5, 21)
X, Y, Z = np.meshgrid(Xf, Xf, Xf, indexing='ij')
Xr, Yr, Zr = X.ravel(), Y.ravel(), Z.ravel()
r = np.sqrt(Xr**2 + Yr**2 + Zr**2)
idx = np.argmin(np.abs(r - 1.05))
bmag_grid = np.sqrt(bx_a[idx]**2 + by_a[idx]**2 + bz_a[idx]**2)
print(f"Grid at nearest to (1.05,0,0): B=({bx_a[idx]:.0f}, {by_a[idx]:.0f}, {bz_a[idx]:.0f}) nT, |B|={bmag_grid:.0f} nT")
print(f"  Actual pos: ({Xr[idx]:.2f}, {Yr[idx]:.2f}, {Zr[idx]:.2f}) Re, r={r[idx]:.2f}")

# Expect near-Earth dipole: B ~ 31000 / r^3 = 31000/1.16 = 26700 nT at equator
print(f"\nExpected dipole at 1.05 Re equator: ~26700 nT")
print(f"Grid value: {bmag_grid:.0f} nT")
if bmag_grid > 10000:
    print("PASS: Grid contains strong near-Earth field (IGRF working correctly)")
else:
    print("FAIL: Near-Earth field too weak")
