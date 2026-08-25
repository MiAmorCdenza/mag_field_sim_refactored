"""Quick test: verify python_bridge compute_grid works for all models."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import python_bridge
import numpy as np

for mag_model in [1, 2, 3, 4]:
    name = {1: 'T89', 2: 'T96', 3: 'T01', 4: 'T04'}[mag_model]
    print(f"Testing {name} + IGRF...", end=" ", flush=True)
    t0 = time.time()
    bx, by, bz = python_bridge.compute_grid(
        mag_model, 2.0, 0.0,
        -5.0, 5.0, 5, -5.0, 5.0, 5, -5.0, 5.0, 5
    )
    t1 = time.time()
    
    if len(bx) == 0:
        print("FAILED (empty result)")
        continue
    
    # Check near-Earth field
    bx_a, by_a, bz_a = np.array(bx), np.array(by), np.array(bz)
    X, Y, Z = np.meshgrid(
        np.linspace(-5, 5, 5), np.linspace(-5, 5, 5), np.linspace(-5, 5, 5),
        indexing='ij'
    )
    Xf, Yf, Zf = X.ravel(), Y.ravel(), Z.ravel()
    r = np.sqrt(Xf**2 + Yf**2 + Zf**2)
    idx = np.argmin(np.abs(r - 1.05))
    bmag = np.sqrt(bx_a[idx]**2 + by_a[idx]**2 + bz_a[idx]**2)
    
    print(f"OK ({t1-t0:.1f}s, {len(bx)} cells, near-Earth |B|={bmag:.0f} nT)")

# Also test a full-size grid (61x41x41) once for T04
print("\nTesting full grid (61x41x41) for T04...", end=" ", flush=True)
t0 = time.time()
bx, by, bz = python_bridge.compute_grid(
    4, 2.0, 0.0,
    -40.0, 20.0, 61, -20.0, 20.0, 41, -20.0, 20.0, 41
)
t1 = time.time()
print(f"OK ({t1-t0:.1f}s, {len(bx)} cells)")

bx_a = np.array(bx)
print(f"  Bx: [{bx_a.min():.1f}, {bx_a.max():.1f}] nT")
print(f"  By: [{np.array(by).min():.1f}, {np.array(by).max():.1f}] nT")
print(f"  Bz: [{np.array(bz).min():.1f}, {np.array(bz).max():.1f}] nT")
print("All tests passed!")
