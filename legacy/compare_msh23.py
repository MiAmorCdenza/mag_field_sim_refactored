"""Compare MSH23 Tsyganenko 2023 magnetosheath model with our analytical draping."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import python_bridge as pb

# Disable progress print
pb.VERBOSE = False

print("=" * 75)
print("MSH23 Tsyganenko 2023 vs Analytical Draping — Comparison")
print("=" * 75)

# Test points: key locations in the magnetosheath
kp = 2.0
ps = 0.3  # ~17 deg dipole tilt
pdyn = 2.0 + kp * 0.5

test_pts = [
    (12.0, 0.0, 0.0,  "Subsolar nose"),
    (10.0, 5.0, 0.0,  "Dayside mid"),
    (10.0, 10.0, 0.0, "Dayside flank"),
    (8.0, 8.0, 0.0,   "Near MP, flank"),
    (5.0, 12.0, 0.0,  "Flank, large Y"),
    (0.0, 15.0, 0.0,  "Terminator, flank"),
    (12.0, 0.0, 8.0,  "High latitude nose"),
]

x_arr = np.array([p[0] for p in test_pts])
y_arr = np.array([p[1] for p in test_pts])
z_arr = np.array([p[2] for p in test_pts])

# Compute with model 1 (uniform IMF)
bx_ext = np.zeros(len(test_pts))  # Tsyganenko external = 0 for comparison
bp = np.zeros(len(test_pts))
bz_base = np.array([0.0]*len(test_pts))
bx1, by1, bz1 = pb._apply_magnetopause_envelope(
    bx_ext.copy(), bx_ext.copy(), bx_ext.copy(),
    x_arr, y_arr, z_arr, tail_model=2, magnetopause_model=1,
    kp=kp, ps=ps)

# Compute with model 2 (analytical draping)
bx2, by2, bz2 = pb._apply_magnetopause_envelope(
    bx_ext.copy(), bx_ext.copy(), bx_ext.copy(),
    x_arr, y_arr, z_arr, tail_model=2, magnetopause_model=2,
    kp=kp, ps=ps)

# Compute with model 3 (MSH23) — only if EXE exists
has_msh23 = os.path.exists(pb.MSH23_EXE)
if has_msh23:
    bx3, by3, bz3 = pb._apply_magnetopause_envelope(
        bx_ext.copy(), bx_ext.copy(), bx_ext.copy(),
        x_arr, y_arr, z_arr, tail_model=0, magnetopause_model=3,
        kp=kp, ps=ps)
else:
    print("\n[WARNING] MSH23 not found, skipping model 3 comparison")

print(f"\n{'Point':<22s} {'Model':>8s} {'Bx':>10s} {'By':>10s} {'Bz':>10s} {'|B|':>10s}")
print("-" * 75)

for i, (x, y, z, label) in enumerate(test_pts):
    b1 = np.sqrt(bx1[i]**2 + by1[i]**2 + bz1[i]**2)
    b2 = np.sqrt(bx2[i]**2 + by2[i]**2 + bz2[i]**2)
    print(f'{label:<22s} {"Mode 1":>8s} {bx1[i]:10.2f} {by1[i]:10.2f} {bz1[i]:10.2f} {b1:10.2f}')
    print(f'{"":22s} {"Mode 2":>8s} {bx2[i]:10.2f} {by2[i]:10.2f} {bz2[i]:10.2f} {b2:10.2f}')
    if has_msh23:
        b3 = np.sqrt(bx3[i]**2 + by3[i]**2 + bz3[i]**2)
        print(f'{"":22s} {"MSH23":>8s} {bx3[i]:10.2f} {by3[i]:10.2f} {bz3[i]:10.2f} {b3:10.2f}')
    print()

print("=" * 75)
print("Legend:")
print("  Mode 1 = Uniform IMF outside MP")
print("  Mode 2 = Analytical draping (image dipole)")
print("  MSH23 = Tsyganenko 2023 magnetosheath (960 coeffs)")
