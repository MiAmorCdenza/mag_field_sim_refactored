# -*- coding: utf-8 -*-
"""Empirical verification of issues found in this codebase."""
import sys, os, traceback
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
try:
    import python_bridge as pb
    print("IMPORT OK")
except Exception:
    traceback.print_exc()
    sys.exit(0)

import numpy as np

def bmag_near_earth(mag_model, mp, tail=0):
    bx, by, bz, xs, ys, zs = pb.compute_grid(mag_model, 2.0, 0.0, tail, mp,
        (-8.0, 8.0, 17), (-8.0, 8.0, 17), (-8.0, 8.0, 17))
    bx = np.array(bx).reshape(len(xs), len(ys), len(zs))
    by = np.array(by).reshape(len(xs), len(ys), len(zs))
    bz = np.array(bz).reshape(len(xs), len(ys), len(zs))
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
    r = np.sqrt(X**2+Y**2+Z**2)
    idx = np.unravel_index(np.argmin(np.abs(r-1.05)), r.shape)
    b = np.sqrt(bx[idx]**2+by[idx]**2+bz[idx]**2)
    return b, (bx[idx], by[idx], bz[idx])

print("=" * 60)
print("1) Default-state grid check: mag_model=1 (T89), tail=0, mp=0")
b0, v0 = bmag_near_earth(1, 0)
print(f"   mp=0: |B| at r~1.05 equator = {b0:.1f} nT  {v0}")
print("   (pure dipole should be ~27000 nT -> mp=0 grid has NO dipole)")
b1, v1 = bmag_near_earth(1, 1)
print(f"   mp=1: |B| at r~1.05 equator = {b1:.1f} nT  {v1}")

print("=" * 60)
print("2) Seasonal tilt sign (day 172 = June solstice)")
for day in [172.0, 355.0, 264.0]:
    tilt = 23.44*np.pi/180*np.cos(2*np.pi*(day-172.0)/365.25) + 11.0*np.pi/180
    mx = -np.sin(tilt); mz = -np.cos(tilt)
    print(f"   day={day}: total_tilt={np.degrees(tilt):+.1f} deg -> dipole moment m=({mx:+.3f}, 0, {mz:+.3f})  (x<0 = tilted AWAY from Sun)")

print("=" * 60)
print("3) Convection E field: implied physical values")
# E_code=5e-6 code-units; B_code=1 <-> 31200 nT; 1 code vel = 6371 km/s
E_code = 5.0e-6
E_real = E_code * 198.8
print(f"   E_conv = {E_code} code = {E_real*1e3:.2f} mV/m (realistic ~0.1-0.5 mV/m)")
for L in [2, 4, 6, 8]:
    B_nT = 31200.0 / L**3
    vd = E_real / (B_nT*1e-9)
    print(f"   L={L}: B={B_nT:.0f} nT, E x B drift = {vd/1000:.2f} km/s")

print("=" * 60)
print("4) Layered atmosphere (atmos_model=1) continuity at boundaries")
def nu(h):
    if h < 100.0:
        return 1000.0*np.exp(-h/8.0)
    elif h < 500.0:
        return 10.0*np.exp(-(h-100.0)/40.0)
    else:
        return 0.5*np.exp(-(h-500.0)/100.0)
for h in [99.9, 100.0, 100.1, 499.9, 500.0, 500.1]:
    print(f"   h={h:6.1f} km: nu={nu(h):.4g} s^-1")
print("   -> jump at 100 km is by factor", f"{nu(100.0)/nu(99.999):.0f}")

print("=" * 60)
print("5) Divergence of the blended grid field (mp=1, tail=2)")
bx, by, bz, xs, ys, zs = pb.compute_grid(4, 2.0, 0.0, 2, 1,
    (-30.0, 15.0, 41), (-15.0, 15.0, 31), (-15.0, 15.0, 31))
bx = np.array(bx).reshape(len(xs), len(ys), len(zs))
by = np.array(by).reshape(len(xs), len(ys), len(zs))
bz = np.array(bz).reshape(len(xs), len(ys), len(zs))
dx = np.gradient(xs); dy = np.gradient(ys); dz = np.gradient(zs)
dbx = np.gradient(bx, dx, axis=0); dby = np.gradient(by, dy, axis=1); dbz = np.gradient(bz, dz, axis=2)
div = dbx + dby + dbz
print(f"   grid divB: mean={np.mean(np.abs(div)):.3f} max={np.max(np.abs(div)):.2f} nT/Re")
print(f"   (reference: |divB|/|B| at MP boundary indicates monopole artifact)")
i, j, k = np.unravel_index(np.argmax(np.abs(div)), div.shape)
print(f"   max divB at ({xs[i]:.1f},{ys[j]:.1f},{zs[k]:.1f}), |B|={np.sqrt(bx[i,j,k]**2+by[i,j,k]**2+bz[i,j,k]**2):.1f} nT")
# also near the dipole-suppression boundary (r ~ 7-9 on dayside)
mask = (np.sqrt(np.meshgrid(xs, ys, zs, indexing='ij')[0]**2 + np.meshgrid(xs, ys, zs, indexing='ij')[1]**2 + np.meshgrid(xs, ys, zs, indexing='ij')[2]**2) > 5)
print(f"   mean|divB| outside r>5: {np.mean(np.abs(div[mask])):.3f} nT/Re, max={np.max(np.abs(div[mask])):.2f} nT/Re")

print("=" * 60)
print("6) sample_diagnostics standalone (works?)")
try:
    res = pb.sample_diagnostics(4, 2.0, 0.0, 2, 1)
    for p in res[:4]:
        print("   ", p["label"], "B=(", p["bx"], p["by"], p["bz"], ") nT  blend_w=", p["blend_w"])
except Exception as e:
    traceback.print_exc()

print("=" * 60)
print("7) Stale test scripts: do they still match the API?")
for fname, args in [("test_bridge.py", None), ("test_igrf.py", None)]:
    pass
try:
    bx, by, bz = pb.compute_grid(1, 2.0, 0.0, -5.0, 5.0, 5, -5.0, 5.0, 5, -5.0, 5.0, 5)
    print("   old 11-arg call: OK")
except TypeError as e:
    print("   old 11-arg call (test_bridge.py style): TypeError ->", str(e)[:100])
print("   hasattr(pb,'VERBOSE'):", hasattr(pb, 'VERBOSE'), "(compare_msh23.py sets pb.VERBOSE=False)")
