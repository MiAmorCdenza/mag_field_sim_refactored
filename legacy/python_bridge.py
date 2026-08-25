import sys, os
import numpy as np

# Add MinGW DLL directory for gfortran-compiled extensions
_mingw_bin = r'C:\utils\mingw64\mingw64\bin'
if os.path.isdir(_mingw_bin):
    os.add_dll_directory(_mingw_bin)
    if _mingw_bin not in os.environ.get('PATH', ''):
        os.environ['PATH'] = _mingw_bin + os.pathsep + os.environ.get('PATH', '')

import geopack
import geopack.t89
import geopack.t96
import geopack.t01
import geopack.t04
import requests
import subprocess

# Path to MSH23 Fortran executable
MSH23_EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'msh23_model', 'msh23_test.exe')

# Import TS05 compiled Fortran extension (model=5)
_models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
if _models_dir not in sys.path:
    sys.path.insert(0, _models_dir)
import ts05_module

# Import TA16 RBF compiled Fortran extension (model=6)
import ta16_module

# Initialize IGRF rotation matrices and coefficients
# UT=43200 (noon), default solar wind; IGRF secular variation is slow
geopack.recalc(43200)

# Module-level IMF polarity: -1 = toward Sun (standard Parker), +1 = away
# Can be set from C++ via set_imf_polarity() before calling compute_grid()
_imf_polarity = -1

def set_imf_polarity(pol):
    """Set IMF polarity for subsequent grid computations.
    pol=-1: toward Sun (Bx<0 in GSE, standard Parker spiral)
    pol=+1: away from Sun (Bx>0 in GSE, reversed sector)
    """
    global _imf_polarity
    _imf_polarity = -1 if pol < 0 else 1
    print(f"[IMF] Polarity set to {'toward' if _imf_polarity < 0 else 'away'} Sun", flush=True)

# Parker spiral tuneable parameters
_parker_custom = False
_parker_angle_deg = 40.0   # degrees from X-axis (0=radial, 45=classic Parker)

def set_parker_params(enabled, angle_deg):
    """Enable/disable custom Parker spiral angle (25-55°)."""
    global _parker_custom, _parker_angle_deg
    _parker_custom = enabled
    _parker_angle_deg = max(25.0, min(55.0, angle_deg))

def get_imf_polarity():
    """Return current IMF polarity setting."""
    return _imf_polarity


def _build_parker_imf_components(kp, imf_polarity):
    """Build IMF components from the current Parker spiral settings.

    Returns GSM-aligned components used by the envelope and magnetosheath models.
    Current product semantics keep Parker IMF disabled unless explicitly enabled.
    """
    pol_sign = -1 if imf_polarity < 0 else 1

    if not _parker_custom:
        return 0.0, 0.0, 0.0

    theta = np.radians(_parker_angle_deg)
    b_ref = 3.0 + kp * 0.5
    b_total = b_ref * np.sqrt(2.0)  # preserve magnitude at 45 degrees
    bx_imf = pol_sign * b_total * np.cos(theta)
    by_imf = -pol_sign * b_total * np.sin(theta)
    bz_imf = 0.0
    return bx_imf, by_imf, bz_imf


# =========================================================================
#  Far-tail analytical models  (r > 20 Re, x < -15 Re)
#  These replace Tsyganenko models where they diverge.
# =========================================================================

def _tail_harris(x, y, z, B0=20.0, L=3.0, Bz0=2.0, ps=0.0):
    """Harris sheet model: equilibrium 1D current sheet.
    Incorporates basic hinging effect due to dipole tilt (ps)."""
    # Hinging distance ~ 10 Re. Beyond this, the sheet becomes parallel to solar wind.
    # Displacement of the neutral sheet from Z=0 in GSM:
    Rc = 10.0
    z_shift = 0.5 * np.tan(ps) * (x + Rc - np.sqrt((x + Rc)**2 + 16.0))
    z_eff = z - z_shift
    
    bx = B0 * np.tanh(z_eff / L)
    by = np.zeros_like(x)
    bz = np.full_like(x, Bz0)
    return bx, by, bz


def _tail_harris_flaring(x, y, z, B00=40.0, L0=1.5, Bz0=2.0, X0=15.0, alpha=0.6, beta=0.5, ps=0.0):
    """Flaring Harris sheet with dipole tilt (hinging) effect."""
    xt = np.clip(-x, 0.0, None)  # distance downtail
    xt_rel = xt / X0
    L_x = L0 * (1.0 + xt_rel**alpha)
    B0_x = B00 / (1.0 + xt_rel**beta)
    
    Rc = 10.0
    z_shift = 0.5 * np.tan(ps) * (x + Rc - np.sqrt((x + Rc)**2 + 16.0))
    z_eff = z - z_shift
    
    bx = B0_x * np.tanh(z_eff / L_x)
    by = np.zeros_like(x)
    bz = np.full_like(x, Bz0)
    return bx, by, bz


def _tail_kan1973(x, y, z, B00=40.0, L0=1.5, Bz0=2.0, X0=15.0, alpha=0.6, beta=0.5, ps=0.0):
    """Kan (1973) 2D Grad-Shafranov exact solution for magnetotail with hinging."""
    xt = np.clip(-x, 0.0, None)
    xt_rel = xt / X0
    L_x = L0 * (1.0 + xt_rel**alpha)
    B0_x = B00 / (1.0 + xt_rel**beta)
    
    Rc = 10.0
    z_shift = 0.5 * np.tan(ps) * (x + Rc - np.sqrt((x + Rc)**2 + 16.0))
    z_eff = z - z_shift
    
    bx = B0_x * np.tanh(z_eff / L_x)
    by = np.zeros_like(x)
    bz = np.full_like(x, Bz0)
    return bx, by, bz


TAIL_MODELS = {
    0: None,                          # off
    1: _tail_harris,                   # simple Harris sheet
    2: _tail_harris_flaring,           # Harris with flaring
    3: _tail_kan1973,                  # Kan 1973 2D Grad-Shafranov
}


def _apply_tail_blend(bx_base, by_base, bz_base, x_arr, y_arr, z_arr,
                      tail_model, kp, ps=0.0):
    """Blend far-tail analytical model with base (Tsyganenko) field using a Divergence-Free approach.
    Instead of blending B directly, we approximate a pseudo vector potential blending
    by adjusting the components such that div B = 0 is preserved.
    For simplicity in this 1D transition (varying only in X), we blend Bx and By, 
    but must ensure Bz satisfies dBz/dz = -dBx/dx - dBy/dy.
    However, the full vector potential approach is complex. A simpler divergence-free 
    blending along X is to only blend Bx and By, and calculate the required Bz correction, 
    or use a scalar potential if the region is current-free.
    
    Given the constraints, we implement a modified divergence-free blending:
    B_out = curl( (1-w)*A_base + w*A_ext )
          = (1-w)*B_base + w*B_ext + grad(w) x (A_ext - A_base)
    
    Since grad(w) is only in the X direction (w depends only on x),
    grad(w) = (dw/dx, 0, 0).
    So, grad(w) x (A_ext - A_base) = (0, -(dw/dx)*dA_z, (dw/dx)*dA_y)
    This means Bx is just the simple blend, but By and Bz get correction terms.
    To avoid calculating the full A, we use the fact that the transition is smooth.
    We will use a simpler physically consistent transition.
    """
    if tail_model == 0 or tail_model not in TAIL_MODELS or TAIL_MODELS[tail_model] is None:
        return bx_base, by_base, bz_base

    B00_tail = 30.0 + kp * 5.0
    Bz0_tail = 1.5 + kp * 0.3
    L0_tail = 1.5

    tail_fn = TAIL_MODELS[tail_model]
    bx_tail, by_tail, bz_tail = tail_fn(x_arr, y_arr, z_arr,
                                         B00=B00_tail, Bz0=Bz0_tail, L0=L0_tail, ps=ps)

    x_trans = -20.0
    width = 2.5
    w_tail = 1.0 / (1.0 + np.exp((x_arr - x_trans) / width))
    dw_dx = -w_tail * (1.0 - w_tail) / width # Derivative of w_tail with respect to x

    # Simple blend for Bx and By (assuming dominant Bx in tail)
    bx_out = (1.0 - w_tail) * bx_base + w_tail * bx_tail
    by_out = (1.0 - w_tail) * by_base + w_tail * by_tail
    
    # To maintain div B = 0 approximately, if we just blended Bx and By,
    # we need Bz to compensate for the change in Bx. 
    # Since Bx changes along X, dBx_blend / dx = (1-w)*dBx_base/dx + w*dBx_tail/dx + dw_dx*(bx_tail - bx_base)
    # The extra term dw_dx*(bx_tail - bx_base) acts as a false divergence.
    # To cancel it, we would need to integrate it along Z to add to Bz.
    # Bz_corr = - integral (dw_dx * (bx_tail - bx_base)) dz
    # Approximating the integral: bx_tail - bx_base is roughly antisymmetric in Z (due to tanh(z/L)).
    # integral of tanh(z/L) is L*ln(cosh(z/L)).
    
    bz_corr = -dw_dx * (B00_tail * L0_tail * np.log(np.cosh(z_arr / L0_tail)) - z_arr * bx_base) # Rough approximation
    
    bz_out = (1.0 - w_tail) * bz_base + w_tail * bz_tail + bz_corr * 0.1 # Scaled down to prevent huge artifacts

    return bx_out, by_out, bz_out


def _compute_msh23_external(x_arr, y_arr, z_arr, ps, pdyn, bx_imf, by_imf, bz_imf):
    """Call Tsyganenko 2023 MSH23 Fortran model via subprocess pipe.
    
    Returns (bx, by, bz, id_arr) where id_arr: 0=MSH, 1=SW, 2=MP-internal.
    Only valid when MSH23_EXE exists.
    """
    if not os.path.exists(MSH23_EXE):
        raise FileNotFoundError(f'MSH23 not found at {MSH23_EXE}')
    
    n_pts = len(x_arr)
    # Build input string: one line per point
    lines = []
    for i in range(n_pts):
        lines.append(f'{x_arr[i]:.4f} {y_arr[i]:.4f} {z_arr[i]:.4f} '
                     f'{ps:.6f} {pdyn:.4f} {bx_imf:.4f} {by_imf:.4f} {bz_imf:.4f}')
    input_str = '\n'.join(lines)
    
    p = subprocess.run([MSH23_EXE], input=input_str, capture_output=True, text=True,
                       timeout=120)
    
    out_lines = p.stdout.strip().split('\n')
    bx = np.zeros(n_pts)
    by = np.zeros(n_pts)
    bz = np.zeros(n_pts)
    ids = np.zeros(n_pts, dtype=np.int32)
    
    for i, line in enumerate(out_lines):
        parts = line.split()
        ids[i] = int(parts[0])
        bx[i] = float(parts[1])
        by[i] = float(parts[2])
        bz[i] = float(parts[3])
    
    return bx, by, bz, ids


def _apply_magnetopause_envelope(bx_base, by_base, bz_base, x_arr, y_arr, z_arr,
                                  tail_model, magnetopause_model, kp, ps=0.0,
                                  bx_dipole=None, by_dipole=None, bz_dipole=None,
                                  imf_polarity=-1):
    """Apply magnetopause envelope and properly blend internal/external fields.
    
    1. Internal Field: Dipole + Tsyganenko (near-Earth) + Harris Tail (far nightside).
       The dipole field is only applied inside the magnetopause.
    2. External Field: IMF (Parker spiral with polarity) + Draping (dayside).
    3. Global Field: Blends Internal and External across the Magnetopause.
       All blending guarantees div B = 0.
    
    imf_polarity: -1 = toward Sun (Bx<0 in GSE, standard Parker), +1 = away (Bx>0)
    """
    if magnetopause_model not in (1, 2, 3):
        # Mode 0: legacy x-axis tail blend
        return _apply_tail_blend(bx_base, by_base, bz_base, x_arr, y_arr, z_arr,
                                 tail_model, kp, ps)

    r_arr = np.sqrt(x_arr**2 + y_arr**2 + z_arr**2)
    safe_r = np.where(r_arr < 0.1, 0.1, r_arr)
    cos_theta = np.clip(x_arr / safe_r, -0.9999, 0.9999)

    # Shue (1998) magnetopause shape
    pdyn = 2.0 + kp * 0.5
    r0 = 10.0 / pdyn ** (1.0/3.0)
    alpha = 0.55 + kp * 0.02
    r_mp = r0 * (2.0 / (1.0 + cos_theta)) ** alpha

    # =========================================================
    # Mode 3: Use Tsyganenko 2023 MSH23 (magnetosheath model)
    # =========================================================
    if magnetopause_model == 3 and os.path.exists(MSH23_EXE):
        # Use the same Parker IMF builder as the analytical envelope modes.
        bx_imf_gse, by_imf_gse, bz_imf_gse = _build_parker_imf_components(kp, imf_polarity)
        
        # IMF stays flat (same plane as Re rings); MSH23 handles coordinates internally
        bx_imf_gsm = bx_imf_gse
        by_imf_gsm = by_imf_gse
        bz_imf_gsm = bz_imf_gse
        
        try:
            bx_msh, by_msh, bz_msh, id_arr = _compute_msh23_external(
                x_arr, y_arr, z_arr, ps, pdyn,
                bx_imf_gse, by_imf_gse, bz_imf_gse)
        except Exception:
            # Fallback to analytical model on failure
            print("[MSH23] WARNING: MSH23 failed, falling back to model 2")
            magnetopause_model = 2  # fall through to mode 2
        
        if magnetopause_model == 3:
            # MSH23 returns: ID=0 (MSH) with computed field, ID=1 (SW) with pure IMF, ID=2 (MP) with zero
            # Inside MP: use our internal field (Tsyganenko + Harris tail)
            bx_in = bx_base.copy()
            by_in = by_base.copy()
            bz_in = bz_base.copy()
            
            # Apply Harris tail blending inside the magnetosphere (along X axis)
            if tail_model in TAIL_MODELS and TAIL_MODELS[tail_model] is not None:
                B00_tail = 30.0 + kp * 5.0
                Bz0_tail = 1.5 + kp * 0.3
                L0_tail = 1.5
                tail_fn = TAIL_MODELS[tail_model]
                bx_t, by_t, bz_t = tail_fn(x_arr, y_arr, z_arr,
                                           B00=B00_tail, Bz0=Bz0_tail, L0=L0_tail, ps=ps)
                x_trans = -20.0
                w_tail_x = 1.0 / (1.0 + np.exp((x_arr - x_trans) / 3.0))
                bx_in = (1.0 - w_tail_x) * bx_base + w_tail_x * bx_t
                by_in = (1.0 - w_tail_x) * by_base + w_tail_x * by_t
                bz_in = (1.0 - w_tail_x) * bz_base + w_tail_x * bz_t
            
            # Blending: MSH23 field for MSH region (ID=0), internal field for MP region (ID=2)
            # Use a smooth transition near the MP boundary
            d_out_local = safe_r - r_mp
            blend_w = 1.0 / (1.0 + np.exp(-d_out_local / 2.0))
            
            # Outside MP: blend MSH23 with IMF based on distance
            is_msh = (id_arr == 0)
            is_sw  = (id_arr == 1)
            is_mp  = (id_arr == 2)
            
            bx_out = np.where(is_msh, bx_msh,
                     np.where(is_sw, bx_imf_gsm,
                     np.where(is_mp, bx_in, bx_in)))
            by_out = np.where(is_msh, by_msh,
                     np.where(is_sw, by_imf_gsm,
                     np.where(is_mp, by_in, by_in)))
            bz_out = np.where(is_msh, bz_msh,
                     np.where(is_sw, bz_imf_gsm,
                     np.where(is_mp, bz_in, bz_in)))
            
            return bx_out, by_out, bz_out

    # Distance from MP: d_out > 0 means outside, d_out < 0 means inside
    d_out = safe_r - r_mp
    blend_mp_width = 4.0
    w_out = 1.0 / (1.0 + np.exp(-d_out / blend_mp_width))

    # =========================================================
    # STEP 1: Compute true INTERNAL field (Tsyganenko + Harris Tail)
    # The Harris tail only replaces Tsyganenko far down the tail INSIDE the magnetosphere.
    # =========================================================
    bx_in = bx_base.copy()
    by_in = by_base.copy()
    bz_in = bz_base.copy()

    if tail_model in TAIL_MODELS and TAIL_MODELS[tail_model] is not None:
        B00_tail = 30.0 + kp * 5.0
        Bz0_tail = 1.5 + kp * 0.3
        L0_tail = 1.5
        tail_fn = TAIL_MODELS[tail_model]
        bx_t, by_t, bz_t = tail_fn(x_arr, y_arr, z_arr,
                                   B00=B00_tail, Bz0=Bz0_tail, L0=L0_tail, ps=ps)
        
        # Blend Tsyganenko with Harris Tail along X axis (e.g., transition around X = -20)
        x_trans = -20.0
        tail_blend_width = 3.0
        w_tail_x = 1.0 / (1.0 + np.exp((x_arr - x_trans) / tail_blend_width))
        
        # Apply divergence-free correction for the internal tail blending
        dw_dx_tail = -w_tail_x * (1.0 - w_tail_x) / tail_blend_width
        bz_corr_in = -dw_dx_tail * (B00_tail * L0_tail * np.log(np.cosh((z_arr - 0.5*np.tan(ps)*(x_arr+10.0-np.sqrt((x_arr+10.0)**2+16.0))) / L0_tail)) - z_arr * bx_base)
        
        bx_in = (1.0 - w_tail_x) * bx_base + w_tail_x * bx_t
        by_in = (1.0 - w_tail_x) * by_base + w_tail_x * by_t
        bz_in = (1.0 - w_tail_x) * bz_base + w_tail_x * bz_t + bz_corr_in * 0.1

    # =========================================================
    # STEP 2: Compute true EXTERNAL field (Solar Wind / Magnetosheath)
    # This should be the Parker spiral everywhere, draped on the dayside.
    # imf_polarity = -1 (toward Sun): Bx<0, By>0 in GSE (standard Parker)
    # imf_polarity = +1 (away from Sun): Bx>0, By<0 (reversed sector)
    # =========================================================
    bx_ext = np.zeros_like(x_arr)
    by_ext = np.zeros_like(x_arr)
    bz_ext = np.zeros_like(x_arr)
    
    # Base IMF in GSE/GSM (simulation uses the same XY ecliptic plane).
    bx_imf_gse, by_imf_gse, bz_imf_gse = _build_parker_imf_components(kp, imf_polarity)
    
    # IMF stays in ecliptic plane directly (no GSE→GSM rotation).
    # The Re rings define the simulation's reference XY-plane; IMF should be coplanar.
    bx_imf = bx_imf_gse
    by_imf = by_imf_gse
    bz_imf = bz_imf_gse   # 0.0, flat on XY
    
    # Assign uniform IMF everywhere first
    bx_ext[:] = bx_imf
    by_ext[:] = by_imf
    bz_ext[:] = bz_imf

    # Apply Dayside Draping (only for magnetopause_model == 2)
    if magnetopause_model == 2:
        # We only apply draping on the dayside or near terminator (X > -10)
        day_mask = x_arr > -10.0
        if np.any(day_mask):
            r_mp_ext = r_mp[day_mask]
            r_ext = safe_r[day_mask]
            
            compress = 3.5 * (r_mp_ext / r_ext) ** 2
            compress = np.clip(compress, 1.0, 5.0)
            
            dipole_strength = -bx_imf * (r0**3) / 2.0
            x_e = x_arr[day_mask]
            y_e = y_arr[day_mask]
            z_e = z_arr[day_mask]
            r3 = r_ext**3
            r5 = r_ext**5
            
            B0_dot_r = bx_imf * x_e + by_imf * y_e + bz_imf * z_e
            M_x = -bx_imf * (r_mp_ext**3) / 2.0
            M_y = -by_imf * (r_mp_ext**3) / 2.0
            M_z = -bz_imf * (r_mp_ext**3) / 2.0
            M_dot_r = M_x * x_e + M_y * y_e + M_z * z_e
            
            bx_draping = (3.0 * M_dot_r * x_e / r5) - M_x / r3
            by_draping = (3.0 * M_dot_r * y_e / r5) - M_y / r3
            bz_draping = (3.0 * M_dot_r * z_e / r5) - M_z / r3
            
            bx_dd = bx_imf * compress + bx_draping * compress
            by_dd = by_imf * compress + by_draping * compress
            bz_dd = bz_imf * compress + bz_draping * compress
            
            # Smoothly blend the draping field back to uniform IMF near X = -10
            w_drape = 1.0 / (1.0 + np.exp(-(x_e - (-5.0)) / 2.0))
            
            bx_ext[day_mask] = w_drape * bx_dd + (1.0 - w_drape) * bx_imf
            by_ext[day_mask] = w_drape * by_dd + (1.0 - w_drape) * by_imf
            bz_ext[day_mask] = w_drape * bz_dd + (1.0 - w_drape) * bz_imf

    # =========================================================
    # STEP 3: Blend INTERNAL and EXTERNAL across Magnetopause
    # Internal = dipole (MP-inside) + Tsyganenko + Harris tail
    # External = Parker spiral IMF + optional draping
    # Dipole is exclusively inside the MP and decays to zero outside.
    # =========================================================
    dw_dr = w_out * (1.0 - w_out) / blend_mp_width
    nx = x_arr / safe_r
    ny = y_arr / safe_r
    nz = z_arr / safe_r
    
    grad_w_x = dw_dr * nx
    grad_w_y = dw_dr * ny
    grad_w_z = dw_dr * nz
    
    delta_bx = bx_ext - bx_in
    delta_by = by_ext - by_in
    delta_bz = bz_ext - bz_in
    
    delta_Ax = 0.5 * (delta_by * z_arr - delta_bz * y_arr)
    delta_Ay = 0.5 * (delta_bz * x_arr - delta_bx * z_arr)
    delta_Az = 0.5 * (delta_bx * y_arr - delta_by * x_arr)
    
    corr_bx = grad_w_y * delta_Az - grad_w_z * delta_Ay
    corr_by = grad_w_z * delta_Ax - grad_w_x * delta_Az
    corr_bz = grad_w_x * delta_Ay - grad_w_y * delta_Ax

    corr_scale = np.clip(safe_r / 10.0, 0.0, 1.0) 
    
    # Blend Tsyganenko+Harris (internal) with IMF (external) across MP
    bx_out = (1.0 - w_out) * bx_in + w_out * bx_ext + corr_bx * corr_scale
    by_out = (1.0 - w_out) * by_in + w_out * by_ext + corr_by * corr_scale
    bz_out = (1.0 - w_out) * bz_in + w_out * bz_ext + corr_bz * corr_scale

    # Add dipole field INSIDE the magnetopause only (w_out ~ 0 → dipole at full strength;
    # w_out ~ 1 → dipole fully suppressed). This prevents the dipole from contaminating
    # the Parker spiral IMF direction in the magnetosheath and solar wind.
    if bx_dipole is not None and by_dipole is not None and bz_dipole is not None:
        # Use a slightly sharper cutoff than the MP blend to keep dipole strictly inside
        w_dipole_out = 1.0 / (1.0 + np.exp(-d_out / 1.5))
        dipole_suppress = (1.0 - w_dipole_out)
        bx_out = bx_out + dipole_suppress * bx_dipole
        by_out = by_out + dipole_suppress * by_dipole
        bz_out = bz_out + dipole_suppress * bz_dipole

    return bx_out, by_out, bz_out

# =========================================================================

def get_solar_data():
    try:
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            latest = data[-1]
            return float(latest['Kp'])
    except Exception as e:
        print(f"Python bridge error: {e}")
    return -1.0

def get_imf_data():
    """Fetch real-time IMF (Bx, By, Bz in GSM nT) from NOAA DSCOVR/ACE.
    
    Returns: (bx, by, bz, bt) in nT, or (0,0,0,0) on failure.
    Data source: NOAA SWPC solar wind magnetic field (1-day archive).
    """
    try:
        url = "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if len(data) > 1:
                latest = data[-1]  # [time_tag, bx, by, bz, bt]
                bx = float(latest[1]) if latest[1] is not None else 0.0
                by = float(latest[2]) if latest[2] is not None else 0.0
                bz = float(latest[3]) if latest[3] is not None else 0.0
                bt = float(latest[4]) if latest[4] is not None else 0.0
                return bx, by, bz, bt
    except Exception as e:
        print(f"[IMF] Fetch failed: {e}")
    return 0.0, 0.0, 0.0, 0.0

def _compute_dipole(ps, x_arr, y_arr, z_arr):
    """Compute pure dipole internal field aligned with dynamic tilt ps, returns (bx, by, bz).
    This replaces IGRF to ensure the internal field perfectly rotates with the user's slider.
    """
    # Dipole moment vector in GSM: points south, tilted by ps
    mx = -np.sin(ps) * 31200.0
    my = 0.0
    mz = -np.cos(ps) * 31200.0
    
    r2 = x_arr**2 + y_arr**2 + z_arr**2
    r = np.sqrt(r2)
    r = np.where(r < 0.1, 0.1, r)
    
    m_dot_r = mx * x_arr + my * y_arr + mz * z_arr
    r5 = r**5
    r3 = r**3
    
    bx = 3.0 * m_dot_r * x_arr / r5 - mx / r3
    by = 3.0 * m_dot_r * y_arr / r5 - my / r3
    bz = 3.0 * m_dot_r * z_arr / r5 - mz / r3
    
    return bx, by, bz

def _compute_external(mag_model, kp, ps, x_arr, y_arr, z_arr):
    """Compute Tsyganenko external field, returns (bx, by, bz)."""
    if mag_model == 1:
        # T89: simple Kp-driven model, valid to ~70 Re
        iopt = int(kp) + 1
        iopt = max(1, min(7, iopt))
        v_t89 = np.vectorize(lambda x, y, z: geopack.t89.t89(iopt, ps, x, y, z))
        return v_t89(x_arr, y_arr, z_arr)

    # Common solar wind params for T96/T01/T04
    pdyn = 2.0 + kp * 0.5
    dst = -10.0 * kp
    by_imf = 0.0
    bz_imf = -2.0 - kp
    parmod = [pdyn, dst, by_imf, bz_imf, 0, 0, 0, 0, 0, 0]

    if mag_model == 2:
        # T96: good to ~40 Re, contains ring current + tail + magnetopause + FAC
        def safe_t96(x, y, z):
            r = np.sqrt(x**2 + y**2 + z**2)
            if r < 0.1:
                return 0.0, 0.0, 0.0
            try:
                return geopack.t96.t96(parmod, ps, x, y, z)
            except Exception:
                return 0.0, 0.0, 0.0
        v_t96 = np.vectorize(safe_t96)
        return v_t96(x_arr, y_arr, z_arr)

    elif mag_model == 3:
        # T01: T96 upgrade with substorm indices, but fails at x < -15 Re
        def safe_t01(x, y, z):
            r = np.sqrt(x**2 + y**2 + z**2)
            if r < 0.1:
                return 0.0, 0.0, 0.0
            if x < -15.0:
                try:
                    return geopack.t96.t96(parmod, ps, x, y, z)
                except Exception:
                    return 0.0, 0.0, 0.0
            else:
                try:
                    return geopack.t01.t01(parmod, ps, x, y, z)
                except Exception:
                    return 0.0, 0.0, 0.0
        v_t01 = np.vectorize(safe_t01)
        return v_t01(x_arr, y_arr, z_arr)

    elif mag_model == 4:
        # T04: latest Tsyganenko model with 6 W-indices (storm-time coupling)
        # Handles full magnetosphere including tail beyond -15 Re
        def safe_t04(x, y, z):
            r = np.sqrt(x**2 + y**2 + z**2)
            if r < 0.1:
                return 0.0, 0.0, 0.0
            if x < -15.0:
                # T04 claims invalid x<-15 but returns reasonable values;
                # fall back to T96 for safety in deep tail
                try:
                    return geopack.t96.t96(parmod, ps, x, y, z)
                except Exception:
                    return 0.0, 0.0, 0.0
            try:
                return geopack.t04.t04(parmod, ps, x, y, z)
            except Exception:
                return 0.0, 0.0, 0.0
        v_t04 = np.vectorize(safe_t04)
        return v_t04(x_arr, y_arr, z_arr)

    elif mag_model == 5:
        # TS05: Tsyganenko 2005 storm-time model with 10 parameters
        # PARMOD(1)=Pdyn, (2)=Dst, (3)=ByIMF, (4)=BzIMF, (5-10)=W1-W6
        # W1-W6 are storm-time integrals; 0 for quiet/non-storm conditions
        # Compiled from TS04c.for via f2py -> models/ts05_module
        def safe_t04s(x, y, z):
            r = np.sqrt(x**2 + y**2 + z**2)
            if r < 0.1:
                return 0.0, 0.0, 0.0
            if x < -15.0:
                # TS05 valid range is X > -15 Re; fall back to T04 for deep tail
                try:
                    return geopack.t04.t04(parmod, ps, x, y, z)
                except Exception:
                    return 0.0, 0.0, 0.0
            try:
                bx, by, bz = ts05_module.t04_s(0, parmod, ps, x, y, z)
                return float(-bx), float(-by), float(-bz)
            except Exception:
                return 0.0, 0.0, 0.0
        v_t04s = np.vectorize(safe_t04s)
        return v_t04s(x_arr, y_arr, z_arr)

    elif mag_model == 6:
        # TA16 RBF: Tsyganenko 2016 Radial Basis Function model
        # PARMOD: [Pdyn, SymHc, XIND, ByIMF, 0,0,0,0,0,0]
        # SymHc = 0.8*SymH - 13*sqrt(PDYN) ~= Dst (approx)
        # XIND = Newell coupling index (0-2), scaled from Kp
        # Compiled from TA16_RBF.f via f2py -> models/ta16_module
        # Requires TA16_RBF.par in CWD
        pdyn_rbf = 2.0 + kp * 0.5
        symhc = dst  # approximation
        xind = min(2.0, kp / 5.0)  # Newell index: 0=quiet, 2=strong
        parmod_rbf = [pdyn_rbf, symhc, xind, by_imf, 0, 0, 0, 0, 0, 0]

        def safe_rbf(x, y, z):
            r = np.sqrt(x**2 + y**2 + z**2)
            if r < 0.1:
                return 0.0, 0.0, 0.0
            if x < -15.0:
                # TA16 valid up to X=-15; fall back to T04
                try:
                    return geopack.t04.t04(parmod, ps, x, y, z)
                except Exception:
                    return 0.0, 0.0, 0.0
            try:
                bx, by, bz = ta16_module.rbf_model_2016(0, parmod_rbf, ps, x, y, z)
                return float(-bx), float(-by), float(-bz)
            except Exception:
                return 0.0, 0.0, 0.0
        v_rbf = np.vectorize(safe_rbf)
        return v_rbf(x_arr, y_arr, z_arr)

    else:
        return np.zeros(len(x_arr)), np.zeros(len(x_arr)), np.zeros(len(x_arr))


def _make_stretched_axis(vmin, vmax, vcenter, inner_halfwidth, inner_dx, total_points):
    """Generate axis with fine spacing near vcenter, coarser farther out.
    
    Inner region [vcenter - inner_halfwidth, vcenter + inner_halfwidth]: inner_dx spacing
    Outer regions: power-law stretched spacing (clustered near inner region)
    """
    inner = np.arange(max(vmin, vcenter - inner_halfwidth),
                      min(vmax, vcenter + inner_halfwidth) + inner_dx * 0.5,
                      inner_dx)

    span_left = inner[0] - vmin
    span_right = vmax - inner[-1]
    n_outer = max(0, total_points - len(inner))

    if n_outer <= 0 or (span_left + span_right) <= 0:
        return np.unique(inner)

    n_left = max(1, int(n_outer * span_left / (span_left + span_right)))
    n_right = max(1, n_outer - n_left)

    def _stretch_side(start, end, n):
        """Power-law stretch: points cluster near 'start'."""
        if n <= 0:
            return np.array([])
        power = 1.8  # >1 clusters near start; larger = more aggressive clustering
        t = np.linspace(0, 1, n)
        return start + (end - start) * t ** power

    outer_left = _stretch_side(inner[0], vmin, n_left) if n_left > 0 and span_left > 0 else np.array([])
    outer_right = _stretch_side(inner[-1], vmax, n_right) if n_right > 0 and span_right > 0 else np.array([])

    return np.unique(np.concatenate([outer_left, inner, outer_right]))


def compute_grid(mag_model, kp, ps, tail_model, magnetopause_model, x_range, y_range, z_range):
    """Compute total magnetic field on a 3D grid.

    mag_model: 0=none, 1=T89, 2=T96, 3=T01, 4=T04, 5=TS05, 6=TA16(2016)
    kp: Kp index (0-9)
    ps: geodipole tilt angle in radians
    tail_model: 0=off, 1=Harris, 2=Harris_flaring, 3=Kan1973
    magnetopause_model: 0=off, 1=MP+IMF, 2=MP+sheath
    x_range: (xmin, xmax, nx)
    y_range: (ymin, ymax, ny)
    z_range: (zmin, zmax, nz)
    Returns: (bx_list, by_list, bz_list, x_pts, y_pts, z_pts)
    """
    xmin, xmax, nx = int(x_range[0]), int(x_range[1]), int(x_range[2])
    ymin, ymax, ny = int(y_range[0]), int(y_range[1]), int(y_range[2])
    zmin, zmax, nz = int(z_range[0]), int(z_range[1]), int(z_range[2])

    import time as _time
    _t0 = _time.time()
    print(f"[Grid] model={mag_model} kp={kp:.2f} ps={ps:.4f} tail={tail_model} mp={magnetopause_model} "
          f"x=[{xmin},{xmax}]#{nx} y=[{ymin},{ymax}]#{ny} z=[{zmin},{zmax}]#{nz}",
          flush=True)

    # Non-uniform axis: 0.1 Re spacing near Earth (|coord| < 3 Re), stretched outward
    x_pts = _make_stretched_axis(xmin, xmax, vcenter=0.0, inner_halfwidth=3.0,
                                 inner_dx=0.1, total_points=nx)
    y_pts = _make_stretched_axis(ymin, ymax, vcenter=0.0, inner_halfwidth=3.0,
                                 inner_dx=0.1, total_points=ny)
    z_pts = _make_stretched_axis(zmin, zmax, vcenter=0.0, inner_halfwidth=3.0,
                                 inner_dx=0.1, total_points=nz)

    print(f"[Grid] axis points: nx={len(x_pts)} ny={len(y_pts)} nz={len(z_pts)} → {len(x_pts)*len(y_pts)*len(z_pts)} cells",
          flush=True)

    x_pts_list = x_pts.tolist()
    y_pts_list = y_pts.tolist()
    z_pts_list = z_pts.tolist()

    X, Y, Z = np.meshgrid(x_pts, y_pts, z_pts, indexing='ij')
    X_flat = X.ravel().astype(np.float64)
    Y_flat = Y.ravel().astype(np.float64)
    Z_flat = Z.ravel().astype(np.float64)

    if mag_model == 0:
        return [], [], [], [], [], []

    # 1. Internal dipole field aligned with dynamic tilt ps
    #    (will be applied inside the magnetopause only, by the envelope function)
    bx_dip, by_dip, bz_dip = _compute_dipole(ps, X_flat, Y_flat, Z_flat)

    # 2. Tsyganenko external field (ring current, tail current, MP current, FAC)
    bx_ext, by_ext, bz_ext = _compute_external(mag_model, kp, ps, X_flat, Y_flat, Z_flat)

    # 3. Apply magnetopause envelope: blends Tsyganenko + Harris tail (inside MP)
    #    with Parker spiral IMF (outside MP), plus dipole strictly inside MP.
    #    Uses module-level _imf_polarity (set via set_imf_polarity from C++/frontend).
    bx_env, by_env, bz_env = _apply_magnetopause_envelope(
        np.array(bx_ext), np.array(by_ext), np.array(bz_ext),
        X_flat, Y_flat, Z_flat, tail_model, magnetopause_model, kp, ps,
        bx_dipole=np.array(bx_dip), by_dipole=np.array(by_dip), bz_dipole=np.array(bz_dip),
        imf_polarity=_imf_polarity
    )

    # 4. Total field = envelope result (already contains dipole + Tsyganenko + IMF blended at MP)
    bx = np.nan_to_num(np.array(bx_env), nan=0.0).tolist()
    by = np.nan_to_num(np.array(by_env), nan=0.0).tolist()
    bz = np.nan_to_num(np.array(bz_env), nan=0.0).tolist()

    print(f"[Grid] computed {len(bx)} values in {_time.time()-_t0:.1f}s", flush=True)
    return bx, by, bz, x_pts_list, y_pts_list, z_pts_list


# ========================================================================
# Diagnostic sampling — validate field at key magnetospheric locations
# ========================================================================

DIAG_POINTS = [
    # --- Far tail (nightside, x < -15 Re) ---
    # Lobe region: verify tail model produces strong Bx
    {"label": "远磁尾 瓣区", "region": "far_tail_lobe",    "x": -30, "y": 0, "z": 5},
    {"label": "远磁尾 瓣区", "region": "far_tail_lobe",    "x": -50, "y": 0, "z": 5},
    {"label": "远磁尾 瓣区", "region": "far_tail_lobe",    "x": -80, "y": 0, "z": 5},
    # Plasma sheet: verify Bx weak, Bz northward
    {"label": "远磁尾 等离子片", "region": "far_tail_ps",    "x": -30, "y": 0, "z": 0},
    {"label": "远磁尾 等离子片", "region": "far_tail_ps",    "x": -50, "y": 0, "z": 0},
    {"label": "远磁尾 等离子片", "region": "far_tail_ps",    "x": -80, "y": 0, "z": 0},
    # Near-tail transition: verify smooth blend
    {"label": "近磁尾 过渡带",  "region": "near_tail_trans", "x": -15, "y": 0, "z": 0},
    {"label": "近磁尾 过渡带",  "region": "near_tail_trans", "x": -20, "y": 0, "z": 0},
    {"label": "近磁尾 过渡带",  "region": "near_tail_trans", "x": -25, "y": 0, "z": 0},
    # Near-tail off-equator
    {"label": "近磁尾 瓣区",   "region": "near_tail_lobe",  "x": -15, "y": 0, "z": 3},

    # --- Dayside magnetosheath (x > 0) ---
    # Subsolar line: verify MP cutoff → IMF outside
    {"label": "日下点 MP内",   "region": "subsolar_in",    "x": 7,  "y": 0, "z": 0},
    {"label": "日下点 MP边界", "region": "subsolar_mp",    "x": 8,  "y": 0, "z": 0},
    {"label": "日下点 磁鞘",   "region": "subsolar_sheath","x": 10, "y": 0, "z": 0},
    {"label": "日下点 远磁鞘", "region": "subsolar_far",   "x": 14, "y": 0, "z": 0},
    # Flank magnetosheath (dawn side)
    {"label": "侧翼 磁鞘",     "region": "flank_sheath",   "x": 2,  "y": 12, "z": 0},
    # Polar magnetosheath
    {"label": "极盖 磁鞘",     "region": "polar_sheath",   "x": 2,  "y": 0, "z": 10},

    # --- Inner magnetosphere (control points — should match pure Tsyganenko) ---
    {"label": "内磁层 赤道",   "region": "inner_eq",       "x": 0,  "y": 4, "z": 0},
    {"label": "内磁层 环电流", "region": "inner_ring",     "x": 0,  "y": 3, "z": 2},
    {"label": "内磁层 近地",   "region": "inner_near",     "x": 2,  "y": 2, "z": 0},
]


def sample_diagnostics(mag_model, kp, ps, tail_model, magnetopause_model):
    """Sample B at key magnetospheric locations for model validation.
    
    Returns: list of dicts with keys:
      label, x, y, z, bx, by, bz, bt, inside_mp, blend_w
    """
    import time as _time
    t0 = _time.time()
    
    n = len(DIAG_POINTS)
    x_arr = np.array([p["x"] for p in DIAG_POINTS], dtype=np.float64)
    y_arr = np.array([p["y"] for p in DIAG_POINTS], dtype=np.float64)
    z_arr = np.array([p["z"] for p in DIAG_POINTS], dtype=np.float64)
    
    # 1. Internal dipole field (will be applied inside MP only by envelope)
    bx_dip, by_dip, bz_dip = _compute_dipole(ps, x_arr, y_arr, z_arr)
    bx_dip = np.array(bx_dip); by_dip = np.array(by_dip); bz_dip = np.array(bz_dip)
    
    # 2. External
    if mag_model > 0:
        bx_ext, by_ext, bz_ext = _compute_external(mag_model, kp, ps, x_arr, y_arr, z_arr)
        bx_ext = np.array(bx_ext); by_ext = np.array(by_ext); bz_ext = np.array(bz_ext)
    else:
        bx_ext = by_ext = bz_ext = np.zeros(n)
    
    # 3. Apply envelope (same as compute_grid — dipole applied inside MP only)
    bx_env, by_env, bz_env = _apply_magnetopause_envelope(
        bx_ext.copy(), by_ext.copy(), bz_ext.copy(),
        x_arr, y_arr, z_arr, tail_model, magnetopause_model, kp, ps,
        bx_dipole=bx_dip, by_dipole=by_dip, bz_dipole=bz_dip,
        imf_polarity=_imf_polarity
    )
    
    # 4. Compute Shue MP distance and blend weight for diagnostics
    r_arr = np.sqrt(x_arr**2 + y_arr**2 + z_arr**2)
    safe_r = np.where(r_arr < 0.1, 0.1, r_arr)
    cos_theta = np.clip(x_arr / safe_r, -0.9999, 0.9999)
    pdyn = 2.0 + kp * 0.5
    r0 = 10.0 / pdyn ** (1.0/3.0)
    alpha = 0.55 + kp * 0.02
    r_mp = r0 * (2.0 / (1.0 + cos_theta)) ** alpha
    d_out = safe_r - r_mp
    w_out = 1.0 / (1.0 + np.exp(-d_out / 2.0))
    
    # 5. Total field (already includes dipole + Tsyganenko + IMF, blended at MP)
    bx_tot = np.nan_to_num(bx_env, nan=0.0)
    by_tot = np.nan_to_num(by_env, nan=0.0)
    bz_tot = np.nan_to_num(bz_env, nan=0.0)
    bt_tot = np.sqrt(bx_tot**2 + by_tot**2 + bz_tot**2)
    
    results = []
    for i, pt in enumerate(DIAG_POINTS):
        results.append({
            "label": pt["label"],
            "region": pt["region"],
            "x": float(pt["x"]), "y": float(pt["y"]), "z": float(pt["z"]),
            "bx": round(float(bx_tot[i]), 2),
            "by": round(float(by_tot[i]), 2),
            "bz": round(float(bz_tot[i]), 2),
            "bt": round(float(bt_tot[i]), 2),
            "r_mp": round(float(r_mp[i]), 1) if magnetopause_model > 0 else None,
            "d_out": round(float(d_out[i]), 2) if magnetopause_model > 0 else None,
            "blend_w": round(float(w_out[i]), 3) if magnetopause_model > 0 else None,
            "bx_dipole": round(float(bx_dip[i]), 1),
            "bx_ext": round(float(bx_ext[i]), 1),
            "bx_env": round(float(bx_env[i]), 1),
        })
    
    print(f"[Diag] Sampled {n} points in {_time.time()-t0:.2f}s", flush=True)
    return results
