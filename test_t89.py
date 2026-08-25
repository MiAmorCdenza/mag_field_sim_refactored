import numpy as np
import time
from geopack import geopack

def test_t89():
    iopt = 2
    # The arguments are iopt, parmod, ps, x, y, z
    # Let's check the signature of t89
    import inspect
    print("t89 signature:", inspect.signature(geopack.t89))
    
    # Try calling it
    try:
        # t89(iopt, parmod, ps, x, y, z) or t89(iopt, x, y, z)?
        # According to documentation it might be:
        # t89(iopt, ps, xgsm, ygsm, zgsm)
        # where ps is the dipole tilt angle.
        
        # In Fortran: SUBROUTINE T89(IOPT,PARMOD,PS,X,Y,Z,BX,BY,BZ)
        # For python wrapper, it usually returns bx, by, bz.
        # Let's try to just read docstring:
        print("Docstring:", geopack.t89.__doc__)
        
        # Try some call:
        res = geopack.t89(2, 0.0, 10.0, 0.0, 0.0)
        print("Result:", res)
    except Exception as e:
        print("Error calling t89:", e)

if __name__ == '__main__':
    test_t89()
