"""场节点对照验证:新引擎烘焙结果 vs 旧管线(legacy python_bridge)逐点对比。

策略:点阵轴 = 诊断点坐标去重 → 诊断点恰为网格角点 → 免插值、逐位精确对照。
运行: python tests/test_field_nodes.py
依赖:系统 Python 3.14(已装 geopack)+ 原项目 models/*.cp314 pyd + 原项目目录。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_DIR = r"C:\Users\Admin\Documents\trae_projects\mag_field_sim"

sys.path.insert(0, ROOT)
sys.path.insert(0, LEGACY_DIR)
sys.path.insert(0, os.path.join(LEGACY_DIR, "models"))

import numpy as np

# 兼容垫片:新版 geopack 将 recalc 等工具移入 geopack.geopack 子模块,
# 旧管线(legacy python_bridge)使用顶层 API。
import geopack
if not hasattr(geopack, "recalc"):
    from geopack import geopack as _gp
    geopack.recalc = _gp.recalc

from engine import default_registry, Graph, Lattice
import python_bridge as legacy  # 旧管线(对照基准)

# 与 legacy python_bridge.DIAG_POINTS 一致的 19 个诊断点
DIAG_POINTS = [
    {"x": -30, "y": 0, "z": 5}, {"x": -50, "y": 0, "z": 5},
    {"x": -80, "y": 0, "z": 5}, {"x": -30, "y": 0, "z": 0},
    {"x": -50, "y": 0, "z": 0}, {"x": -80, "y": 0, "z": 0},
    {"x": -15, "y": 0, "z": 0}, {"x": -20, "y": 0, "z": 0},
    {"x": -25, "y": 0, "z": 0}, {"x": -15, "y": 0, "z": 3},
    {"x": 7, "y": 0, "z": 0}, {"x": 8, "y": 0, "z": 0},
    {"x": 10, "y": 0, "z": 0}, {"x": 14, "y": 0, "z": 0},
    {"x": 2, "y": 12, "z": 0}, {"x": 2, "y": 0, "z": 10},
    {"x": 0, "y": 4, "z": 0}, {"x": 0, "y": 3, "z": 2},
    {"x": 2, "y": 2, "z": 0},
]

KP, PS = 2.0, 0.5


def diag_lattice():
    xs = sorted({p["x"] for p in DIAG_POINTS})
    ys = sorted({p["y"] for p in DIAG_POINTS})
    zs = sorted({p["z"] for p in DIAG_POINTS})
    return Lattice(xs, ys, zs)


def make_registry():
    reg = default_registry()
    types = reg.list_types()
    need = ["kp_source", "day_source", "imf_source", "dipole", "t89",
            "tail", "tail_blend", "internal_blend", "magnetopause",
            "convection", "corotation", "volland_shield", "mul", "add",
            "drag_layered", "output_slot"]
    missing = [t for t in need if t not in types]
    assert not missing, f"注册表缺节点: {missing}"
    print(f"✓ 注册表加载 {len(types)} 种节点")
    return reg


def build(reg, mode):
    """mode: A=t89裸 / B=+tail(mp=0) / C=+包边mp=1(IMF关) / D=+包边mp=2(帕克开)"""
    g = Graph(reg, diag_lattice())
    g.add_node("kp", "kp_source", {"kp": KP})
    g.add_node("t89", "t89", input_defaults={"kp": KP, "ps": PS})
    g.connect("kp", "kp", "t89", "kp")

    if mode == "A":
        g.add_node("blend", "tail_blend", input_defaults={"kp": KP, "ps": PS})
        g.add_node("mp", "magnetopause", {"mp_model": 0})
        g.connect("t89", "field", "blend", "base")
        g.connect("blend", "field", "mp", "internal")
        g.declare_output("B", "mp", "field")
    else:
        g.add_node("tail", "tail", {"model": "flaring"},
                   input_defaults={"kp": KP, "ps": PS})
        g.add_node("dipole", "dipole", input_defaults={"ps": PS})
        g.add_node("imf", "imf_source",
                   {"parker_custom": mode == "D", "parker_angle": 40.0, "polarity": -1},
                   input_defaults={"kp": KP})
        if mode == "B":
            g.add_node("blend", "tail_blend", input_defaults={"kp": KP, "ps": PS})
            g.add_node("mp", "magnetopause", {"mp_model": 0})
            g.connect("t89", "field", "blend", "base")
            g.connect("tail", "field", "blend", "tail")
            g.connect("blend", "field", "mp", "internal")
        else:
            g.add_node("internal", "internal_blend",
                       input_defaults={"kp": KP, "ps": PS})
            g.add_node("mp", "magnetopause", {"mp_model": 1 if mode == "C" else 2},
                       input_defaults={"kp": KP, "ps": PS})
            g.connect("t89", "field", "internal", "base")
            g.connect("tail", "field", "internal", "tail")
            g.connect("internal", "field", "mp", "internal")
            g.connect("dipole", "field", "mp", "dipole")
            g.connect("imf", "field", "mp", "imf")
        g.declare_output("B", "mp", "field")
    return g


def legacy_ref(mode):
    """调用旧管线原始函数(不经 sample_diagnostics 的四舍五入)得到基准值。"""
    legacy.set_imf_polarity(-1)
    legacy.set_parker_params(mode == "D", 40.0)
    tail_model = 0 if mode == "A" else 2
    mp_model = {"A": 0, "B": 0, "C": 1, "D": 2}[mode]

    x = np.array([p["x"] for p in DIAG_POINTS], dtype=np.float64)
    y = np.array([p["y"] for p in DIAG_POINTS], dtype=np.float64)
    z = np.array([p["z"] for p in DIAG_POINTS], dtype=np.float64)

    bx_dip, by_dip, bz_dip = legacy._compute_dipole(PS, x, y, z)
    bx_ext, by_ext, bz_ext = legacy._compute_external(1, KP, PS, x, y, z)
    bx_env, by_env, bz_env = legacy._apply_magnetopause_envelope(
        np.array(bx_ext), np.array(by_ext), np.array(bz_ext),
        x, y, z, tail_model, mp_model, KP, PS,
        bx_dipole=np.array(bx_dip), by_dipole=np.array(by_dip),
        bz_dipole=np.array(bz_dip), imf_polarity=-1)
    return (np.nan_to_num(bx_env), np.nan_to_num(by_env),
            np.nan_to_num(bz_env))


def compare(mode):
    g = build(make_registry(), mode)
    baked = g.bake(["B"])["B"]
    lat = g.lattice
    bx = np.asarray(baked["bx"]).reshape(lat.nx, lat.ny, lat.nz)
    by = np.asarray(baked["by"]).reshape(lat.nx, lat.ny, lat.nz)
    bz = np.asarray(baked["bz"]).reshape(lat.nx, lat.ny, lat.nz)
    ref_bx, ref_by, ref_bz = legacy_ref(mode)

    max_abs = 0.0
    for idx, pt in enumerate(DIAG_POINTS):
        i = int(np.searchsorted(lat.xs, pt["x"]))
        j = int(np.searchsorted(lat.ys, pt["y"]))
        k = int(np.searchsorted(lat.zs, pt["z"]))
        for new, old, name in ((bx[i, j, k], ref_bx[idx], "bx"),
                               (by[i, j, k], ref_by[idx], "by"),
                               (bz[i, j, k], ref_bz[idx], "bz")):
            d = abs(new - old)
            max_abs = max(max_abs, d)
            assert d < 1e-9, (f"[{mode}] ({pt['x']},{pt['y']},{pt['z']}) {name}: "
                              f"new={new} legacy={old}")
    print(f"✓ 模式 {mode}:19 点 × 3 分量与旧管线一致(max|Δ|={max_abs:.2e})")


def test_default_graph_json():
    """默认图 JSON 加载 + 烘焙冒烟(小点阵)。"""
    import json
    reg = make_registry()
    g = Graph(reg, diag_lattice())
    with open(os.path.join(ROOT, "graphs", "default_field_graph.json"),
              encoding="utf-8") as f:
        g.load_json(json.load(f))
    out = g.bake(["B"])
    assert set(out["B"]) == {"xs", "ys", "zs", "bx", "by", "bz"}
    print("✓ 默认图 JSON 加载与烘焙正常")


def test_e_decomposition():
    """E 场原子分解:add(corotation, mul(convection, shield)) 与旧复合公式逐位一致。

    旧公式(legacy efield_model=1):E = (0,5e-6·shielding,0) - (Ω×r)×(B/31200),
    其中 shielding = (r/4)² (0.1<r<4) 否则 1。
    """
    reg = make_registry()
    g = Graph(reg, diag_lattice())
    g.add_node("kp", "kp_source", {"kp": KP})
    g.add_node("t89", "t89", input_defaults={"kp": KP, "ps": PS})
    g.connect("kp", "kp", "t89", "kp")
    g.add_node("tail", "tail", {"model": "flaring"}, input_defaults={"kp": KP, "ps": PS})
    g.add_node("dipole", "dipole", input_defaults={"ps": PS})
    g.add_node("imf", "imf_source",
               {"parker_custom": True, "parker_angle": 40.0, "polarity": -1},
               input_defaults={"kp": KP})
    g.add_node("internal", "internal_blend", input_defaults={"kp": KP, "ps": PS})
    g.add_node("mp", "magnetopause", {"mp_model": 2}, input_defaults={"kp": KP, "ps": PS})
    g.connect("t89", "field", "internal", "base")
    g.connect("tail", "field", "internal", "tail")
    g.connect("internal", "field", "mp", "internal")
    g.connect("dipole", "field", "mp", "dipole")
    g.connect("imf", "field", "mp", "imf")

    # E 原子链:conv × shield + corot
    g.add_node("conv", "convection", {"multiplier": 1.0})
    g.add_node("corot", "corotation")
    g.add_node("shield", "volland_shield", {"r0": 4.0})
    g.add_node("emul", "mul")
    g.add_node("eadd", "add")
    g.connect("mp", "field", "corot", "b")
    g.connect("conv", "field", "emul", "a")
    g.connect("shield", "coef", "emul", "w")
    g.connect("corot", "field", "eadd", "a")
    g.connect("emul", "field", "eadd", "b")
    g.declare_output("B", "mp", "field")
    g.declare_output("E", "eadd", "field")

    baked = g.bake(["B", "E"])
    lat = g.lattice
    bx = np.asarray(baked["B"]["bx"]).reshape(lat.nx, lat.ny, lat.nz)
    by = np.asarray(baked["B"]["by"]).reshape(lat.nx, lat.ny, lat.nz)
    bz = np.asarray(baked["B"]["bz"]).reshape(lat.nx, lat.ny, lat.nz)
    ex = np.asarray(baked["E"]["bx"]).reshape(lat.nx, lat.ny, lat.nz)
    ey = np.asarray(baked["E"]["by"]).reshape(lat.nx, lat.ny, lat.nz)
    ez = np.asarray(baked["E"]["bz"]).reshape(lat.nx, lat.ny, lat.nz)

    omega = 7.27e-5
    scale = 1.0 / 31200.0
    max_d = 0.0
    for pt in DIAG_POINTS:
        i = int(np.searchsorted(lat.xs, pt["x"]))
        j = int(np.searchsorted(lat.ys, pt["y"]))
        k = int(np.searchsorted(lat.zs, pt["z"]))
        x, y, z = pt["x"], pt["y"], pt["z"]
        r = np.sqrt(x * x + y * y + z * z)
        # 共转:-(Ω×r)×B_norm
        vx, vy, vz = -omega * y, omega * x, 0.0
        bxn, byn, bzn = bx[i, j, k] * scale, by[i, j, k] * scale, bz[i, j, k] * scale
        cx = -(vy * bzn - vz * byn)
        cy = -(vz * bxn - vx * bzn)
        cz = -(vx * byn - vy * bxn)
        # 屏蔽对流
        shielding = (r / 4.0) ** 2 if (0.1 < r < 4.0) else 1.0
        ref = (cx, cy + 5.0e-6 * shielding, cz)
        for got, want in ((ex[i, j, k], ref[0]), (ey[i, j, k], ref[1]),
                          (ez[i, j, k], ref[2])):
            max_d = max(max_d, abs(got - want))
            assert abs(got - want) < 1e-12, (
                f"E({x},{y},{z}): graph={got} legacy={want}")
    print(f"✓ E 原子分解与旧复合公式一致(max|Δ|={max_d:.2e})")


if __name__ == "__main__":
    compare("A")
    compare("B")
    compare("C")
    compare("D")
    test_default_graph_json()
    test_e_decomposition()
    print("\n全部场节点对照验证通过 ✅")
