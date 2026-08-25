import numpy as np
import time
from geopack import geopack

def test_grid():
    t0 = time.time()
    
    # 51 x 41 x 41 = 85,731 points
    x = np.linspace(-30, 15, 51)
    y = np.linspace(-20, 20, 41)
    z = np.linspace(-20, 20, 41)
    
    X, Y, Z = np.meshgrid(x, y, z, indexing='ij')
    
    X_flat = X.flatten()
    Y_flat = Y.flatten()
    Z_flat = Z.flatten()
    
    print(f"Points: {len(X_flat)}")
    
    t1 = time.time()
    
    iopt = 2
    try:
        bxgsm, bygsm, bzgsm = geopack.t89.t89(iopt, 0.0, 10.0, 0.0, 0.0)
        print("Result single:", bxgsm, bygsm, bzgsm)
        
        # Test vectorization performance
        v_t89 = np.vectorize(lambda x,y,z: geopack.t89.t89(iopt, 0.0, x, y, z))
        t2 = time.time()
        bx, by, bz = v_t89(X_flat, Y_flat, Z_flat)
        t3 = time.time()
        print(f"Vectorized {len(X_flat)} points took {t3-t2:.3f} s")
    except Exception as e:
        print("Error:", e)
        
if __name__ == '__main__':
    test_grid()
