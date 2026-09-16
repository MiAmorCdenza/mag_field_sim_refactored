"""倾角统一(#42)验收:一个倾角源 → 偶极子 / T89 / A2000 三者倾角必须一致。

背景(用户提出):A2000 的倾角原本只能靠"改日期"间接调,而且和偶极强度耦合;
而偶极子/T89 都是直接吃 `ps`。于是把倾角统一为**显式输入**:
  · 新增 `倾角源` 节点(日期/UT → ps、B0),内部直接调用 A2000 的 TRANS/IDD
    → 换算器与模型**同一份数学**,倾角天然一致(实测 Δψ = 0)
  · `A2000 抛物面(内场)` 增 `ps` 输入:留空 = 用日期算;接了 = 覆盖 par(1)

判据:
  1. 换算器 ψ 与 A2000 内部 par(1) 逐位一致
  2. 同一张图里 偶极子 / A2000 拿到的 ps **完全相同**(接线统一)
  3. A2000 的 ps 覆盖真的生效(改 ps → 场变;且与"直接用内部日期算的同一个 ψ"等价)

运行:python tests/test_tilt_unify.py(需先 scripts\\build_a2000.ps1)
"""
import functools
import os
import sys

import numpy as np

print = functools.partial(print, flush=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import Registry, Graph, Lattice          # noqa: E402
from nodes.paraboloid import _load_lib, _StdoutSilencer  # noqa: E402


def _registry():
    reg = Registry([os.path.join(ROOT, "nodes")])
    reg.scan()
    return reg


def _graph(doc):
    g = Graph(_registry(), Lattice.from_json(doc.get("lattice") or {"preset": "tiny"}))
    g.load_json(doc)
    return g


def test_converter_matches_model():
    import ctypes
    lib = _load_lib()
    D, P, I = ctypes.c_double, ctypes.POINTER(ctypes.c_double), ctypes.c_int
    bimf = np.array([0.0, 0.0, -2.0])
    worst = 0.0
    for (ut, y, mo, d) in ((12.0, 2026, 6, 21), (1.0, 2026, 9, 16),
                           (18.0, 2026, 12, 21), (6.0, 2000, 3, 20)):
        psi, bd = D(0), D(0)
        with _StdoutSilencer():
            lib.a2000_tilt(ut, y, mo, d, ctypes.byref(psi), ctypes.byref(bd))
            lib.a2000_set_time(ut, y, mo, d)
            par = np.zeros(10)
            ifail = I(0)
            lib.a2000_params(5.0, 400.0, bimf.ctypes.data_as(P), -30.0, -100.0,
                             par.ctypes.data_as(P), ctypes.byref(ifail))
        worst = max(worst, abs(psi.value - par[0]), abs(bd.value - par[1]))
    assert worst == 0.0, f"换算器与模型内部倾角不一致:{worst}"
    print("✓ 日期→倾角换算器与 A2000 内部逐位一致(Δψ = ΔB0 = 0,同一份 TRANS/IDD)")


def test_single_tilt_source():
    """预设里 偶极子 与 A2000 必须拿到同一个 ps(接线统一)。"""
    import json
    with open(os.path.join(ROOT, "graphs", "preset_compare_fields.json"),
              encoding="utf-8") as f:
        doc = json.load(f)
    g = _graph(doc)
    # 倾角源算出来的 ps
    tilt_ps = g._eval_node("tilt")["ps"]
    # 偶极子端口上收到的 ps(接线驱动 → 引擎按 inputs_map 取上游标量)
    dip_ps = g._eval_port("dip", "ps")
    assert abs(float(tilt_ps) - float(dip_ps)) < 1e-9, (tilt_ps, dip_ps)
    # A2000 内部实际使用的 par(1)(覆盖后)
    g.evaluate(["B"])
    pb_par1 = float(g.nodes["pb"].last_par[0])
    # A2000 的 par(1) 与我们的 ps **符号相反**(实测:赤道侧面 B_x 判据),
    # 所以"朝向一致"体现为数值反号 —— 物理朝向由 test_convention_matches_dipole 校验
    assert abs(pb_par1 + float(tilt_ps)) < 1e-9, (pb_par1, tilt_ps)
    print("✓ 一个倾角源同时驱动 偶极子(ps=%.3f°) 与 A2000(par(1)=%.3f°):"
          "物理朝向一致、标签反号" % (float(dip_ps), pb_par1))


def test_ps_override_changes_field():
    """ps 覆盖必须真的改场,且等价于"内部日期算出的同一 ψ"。"""
    base = {"version": 1, "lattice": {"preset": "tiny"}, "nodes": [
        {"id": "pb", "type": "paraboloid",
         "input_defaults": {"dst": -30.0, "ps": None},
         "params": {"year": 2026, "month": 6, "day": 21, "ut": 12.0}},
        {"id": "ob", "type": "output_slot", "params": {"slot": "B"}}],
        "edges": [{"from": ["pb", "field"], "to": ["ob", "field"]}], "outputs": {}}
    import copy
    g0 = _graph(base)
    b0 = g0.evaluate(["B"])["B"].data.copy()
    psi0 = float(g0.nodes["pb"].last_par[0])          # 模型内部的 par(1)(与 ps 反号)

    d1 = copy.deepcopy(base)
    d1["nodes"][0]["input_defaults"]["ps"] = 0.0      # 显式压到 0°
    g1 = _graph(d1)
    b1 = g1.evaluate(["B"])["B"].data
    assert abs(float(g1.nodes["pb"].last_par[0])) < 1e-9
    diff = float(np.max(np.abs(b0 - b1)))
    assert diff > 1.0, "ps 覆盖没生效(场几乎没变)"
    print("✓ ps 覆盖生效:ψ=%.2f°(日期) vs ψ=0° → 场最大差 %.1f nT" % (psi0, diff))

    d2 = copy.deepcopy(base)
    # 覆盖成"日期算出的同一个倾角"必须取负:ps 是我们的约定,par(1) 是模型的
    d2["nodes"][0]["input_defaults"]["ps"] = -psi0
    g2 = _graph(d2)
    b2 = g2.evaluate(["B"])["B"].data
    assert float(np.max(np.abs(b0 - b2))) < 1e-6, "显式 ps = −par(1) 时结果应完全一致"
    print("✓ 显式 ps 与「日期算出的同一 ψ」等价(场最大差 < 1e-6 nT)")


def test_convention_matches_dipole():
    """**符号约定**必须一致:同一个 ps 喂给 偶极子 与 A2000,赤道侧面 B_x 同号。

    判据来自实测:A2000 的 par(1) 与 geopack/T89/本项目 ps 符号相反
    (夏至模型内部 ψ=−25.8°,而其场等效于 ps=+25.8°)。
    """
    pt = (0.0, 2.0, 0.0)

    def dip_bx(ps):
        doc = {"version": 1, "lattice": {"preset": "tiny"}, "nodes": [
            {"id": "d", "type": "dipole", "input_defaults": {"ps": ps}},
            {"id": "o", "type": "output_slot", "params": {"slot": "B"}}],
            "edges": [{"from": ["d", "field"], "to": ["o", "field"]}], "outputs": {}}
        g = _graph(doc)
        B = g.evaluate(["B"])["B"].data
        lat = g.lattice
        i = int(np.argmin(abs(lat.xs - pt[0])))
        j = int(np.argmin(abs(lat.ys - pt[1])))
        k = int(np.argmin(abs(lat.zs - pt[2])))
        return float(B[i, j, k][0])

    def a2000_bx(ps):
        doc = {"version": 1, "lattice": {"preset": "tiny"}, "nodes": [
            {"id": "pb", "type": "paraboloid",
             "input_defaults": {"ps": ps, "dst": -30.0}},
            {"id": "o", "type": "output_slot", "params": {"slot": "B"}}],
            "edges": [{"from": ["pb", "field"], "to": ["o", "field"]}],
            "outputs": {}}
        g = _graph(doc)
        B = g.evaluate(["B"])["B"].data
        lat = g.lattice
        i = int(np.argmin(abs(lat.xs - pt[0])))
        j = int(np.argmin(abs(lat.ys - pt[1])))
        k = int(np.argmin(abs(lat.zs - pt[2])))
        return float(B[i, j, k][0])

    for ps in (20.0, -20.0):
        bd, ba = dip_bx(ps), a2000_bx(ps)
        assert bd * ba > 0, (f"ps={ps}: 偶极 B_x={bd:.1f} 与 A2000 B_x={ba:.1f} 反号 "
                             f"→ 倾角约定不一致")
    print("✓ 符号约定一致:ps=±20° 时 偶极 与 A2000 的赤道侧面 B_x 同号"
          "(B_x(%+.0f°)=%+.0f vs %+.0f)"
          % (20.0, dip_bx(20.0), a2000_bx(20.0)))

    # 倾角源导出标准约定:夏至应为正(北轴朝日),而模型内部 TRANS 是负
    import ctypes
    lib = _load_lib()
    psi, bd = ctypes.c_double(0), ctypes.c_double(0)
    with _StdoutSilencer():
        lib.a2000_tilt(12.0, 2026, 6, 21, ctypes.byref(psi), ctypes.byref(bd))
    doc = {"version": 1, "lattice": {"preset": "tiny"}, "nodes": [
        {"id": "t", "type": "tilt_source",
         "params": {"year": 2026, "month": 6, "day": 21, "ut": 12.0}}],
        "edges": [], "outputs": {}}
    src = float(_graph(doc)._eval_node("t")["ps"])
    assert psi.value < 0 < src and abs(src + psi.value) < 1e-9, (psi.value, src)
    print("✓ 倾角源导出标准约定:夏至 %.3f°(模型内部 TRANS 为 %.3f°,已取负)"
          % (src, psi.value))


if __name__ == "__main__":
    test_converter_matches_model()
    test_single_tilt_source()
    test_ps_override_changes_field()
    test_convention_matches_dipole()
    print("\n倾角统一验收全部通过 ✅")
