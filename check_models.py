"""
Check geopack Tsyganenko models: coverage radius range.
Tests T89, T96, T01, T04 along GSE axes to verify valid radius range.
"""
import numpy as np
import geopack

# --- Model parameters ---
# T89: iopt maps to Kp (1=Kp0, 2=Kp1, ..., 7=Kp>=6-)
iopt_t89 = 3  # Kp=2
ps = 0.0      # dipole tilt = 0 (equinox)

# T96: parmod[0:4] = [pdyn(nPa), Dst(nT), ByIMF(nT), BzIMF(nT)]
parmod_t96 = np.zeros(10)
parmod_t96[0] = 2.0   # Pdyn
parmod_t96[1] = -10.0 # Dst
parmod_t96[2] = 0.0   # ByIMF
parmod_t96[3] = -2.0  # BzIMF

# T01: parmod similar, plus G1,G2 for substorm indices
parmod_t01 = np.zeros(10)
parmod_t01[0] = 2.0
parmod_t01[1] = -10.0
parmod_t01[2] = 0.0
parmod_t01[3] = -2.0
parmod_t01[4] = 5.0   # G1
parmod_t01[5] = 10.0  # G2

# T04: parmod with more storm indices
parmod_t04 = np.zeros(10)
parmod_t04[0] = 2.0
parmod_t04[1] = -10.0
parmod_t04[2] = 0.0
parmod_t04[3] = -2.0
parmod_t04[4] = 5.0
parmod_t04[5] = 10.0
# W1-W6 at indices 4-9 are optional

# Test distances in Re (along GSE axes)
distances_re = [1.05, 1.5, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]

models_to_test = [
    ("T89", geopack.t89, lambda r, xsign: (iopt_t89, ps, xsign*r, 0.0, 0.0), 70),
    ("T96", geopack.t96, lambda r, xsign: (parmod_t96, ps, xsign*r, 0.0, 0.0), 40),
]

# Check if t01 and t04 exist in this version
has_t01 = hasattr(geopack, 't01')
has_t04 = hasattr(geopack, 't04')
if has_t01:
    models_to_test.append(("T01", geopack.t01, lambda r, xsign: (parmod_t01, ps, xsign*r, 0.0, 0.0), 50))
if has_t04:
    models_to_test.append(("T04", geopack.t04, lambda r, xsign: (parmod_t04, ps, xsign*r, 0.0, 0.0), 50))

print("=" * 95)
print("Tsyganenko 磁层模型 — 半径覆盖范围检查")
print("测试条件: Kp≈2 (地磁宁静), 偶极倾角=0 (春/秋分), 赤道面 (Z=0)")
print("坐标系: GSM, 单位: Re (1 Re = 6371.2 km)")
print("方向: sun=向日(+X), tail=背日(-X)")
print("=" * 95)

for model_name, model_func, args_func, nominal_max in models_to_test:
    print(f"\n{'─' * 80}")
    print(f"  {model_name} — 标称最大范围: ~{nominal_max} Re")
    print(f"  {'R[Re]':>7} {'方向':>5} {'Bx[nT]':>10} {'By[nT]':>10} {'Bz[nT]':>10} {'|B|[nT]':>10}  状态")
    print(f"  {'─' * 67}")
    
    for r in distances_re:
        for xsign, label in [(1.0, 'sun(+X)'), (-1.0, 'tail(-X)')]:
            try:
                args = args_func(r, xsign)
                Bx, By, Bz = model_func(*args)
                Bmag = np.sqrt(Bx**2 + By**2 + Bz**2)
                
                # Check: is field physically reasonable?
                # Near Earth (r=1.05): B ~ 30000 nT (dipole surface ~31000 nT at equator)
                # At 10 Re: B ~ tens of nT
                # Beyond magnetopause (~10 Re sunward): B ~ 0 or IMF-level (few nT)
                flag = ""
                if r <= 2.0 and Bmag < 100:
                    flag = " ⚠ 近地磁场过弱"
                elif r >= 60 and Bmag > 1000:
                    flag = " ⚠ 远处异常大"
                
                print(f"  {r:>7.1f} {label:>5} {Bx:>10.3f} {By:>10.3f} {Bz:>10.3f} {Bmag:>10.3f} {flag}")
                
            except Exception as e:
                print(f"  {r:>7.1f} {label:>5} {'ERR':>10} {'ERR':>10} {'ERR':>10} {'ERR':>10}  {str(e)[:30]}")

# =============================================
# Azimuthal scan at 6 Re
# =============================================
print(f"\n{'=' * 95}")
print("环向扫描: R = 6 Re 赤道面, MLT 0→24 (验证全天区覆盖)")
print(f"{'=' * 95}")

models_az = [("T96", geopack.t96, parmod_t96)]
if has_t01:
    models_az.append(("T01", geopack.t01, parmod_t01))
if has_t04:
    models_az.append(("T04", geopack.t04, parmod_t04))

header = f"  {'MLT[h]':>7} {'X_GSM[Re]':>10} {'Y_GSM[Re]':>10}"
for mn, _, _ in models_az:
    header += f" {'Bz_'+mn+'[nT]':>14}"
print(header)
print(f"  {'─' * (27 + 14*len(models_az))}")

r0 = 6.0
for mlt_h in np.arange(0, 24, 3):
    phi = np.radians((mlt_h - 12) * 15.0)
    x = r0 * np.cos(phi)
    y = r0 * np.sin(phi)
    
    line = f"  {mlt_h:>7.1f} {x:>10.3f} {y:>10.3f}"
    for mn, mf, pm in models_az:
        try:
            if mn == "T96" or mn == "T01" or mn == "T04":
                _, _, Bz = mf(pm, ps, x, y, 0.0)
            else:
                _, _, Bz = mf(iopt_t89, ps, x, y, 0.0)
            line += f" {Bz:>14.3f}"
        except Exception as e:
            line += f" {'ERR':>14}"
    print(line)

# =============================================
# Summary
# =============================================
print(f"\n{'=' * 95}")
print("总结与建议")
print(f"{'=' * 95}")
print("""
T89:  最简单，仅依赖 Kp，标称范围 70 Re。适合初步测试。
T96:  依赖 Pdyn/Dst/ByIMF/BzIMF，标称范围 ~30-40 Re（磁层顶附近有效）。
      包含环电流、磁尾电流、磁层顶电流、Region-1/2 场向电流。
T01:  T96 的升级版，添加了亚暴指数 G1/G2，标称 ~40-50 Re。
T04:  最新版本，添加了 6 个 W 指数（太阳风-磁层耦合参数），标称 ~40-50 Re。
      对暴时磁层表现最好。

所有模型覆盖 GSM 坐标系的 XY 全平面,Z 方向受偶极倾角调制。
对于"整个地磁泡"需求：T96 是中层选择，T04 是最佳选择。
""")
