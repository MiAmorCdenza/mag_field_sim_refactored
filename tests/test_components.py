"""框架组件逐项验证:以 graphs/minimal_preset.json 为基础。

A 部分(纯引擎,无服务器):注册表 / 图加载 / 三域布局 / 场烘焙 /
粒子计划 / 渲染绑定 / JSON 往返
B 部分(WS,需服务器已启动):烘焙管线 / 几何帧 / 粒子帧推进 /
参数热更新 / respawn / 插件热加载

运行:
  python tests/test_components.py             # 仅 A
  python tests/test_components.py --ws        # A + B(服务器已启动)
"""
import argparse
import asyncio
import functools
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np

from engine.registry import default_registry
from engine.graph import Graph

print = functools.partial(print, flush=True)
PRESET = os.path.join(ROOT, "graphs", "minimal_preset.json")


# ================= A 部分:纯引擎 =================

def part_a():
    reg = default_registry()
    types = reg.list_types()
    domains = {t: reg.get(t)._node_spec.get("domain", "field") for t in types}

    # C1 注册表:三域节点齐备
    for t in ("dipole", "boris_integrator", "leapfrog_integrator",
              "rk4_integrator", "verlet_integrator", "output_encoder",
              "render_pipeline_start", "render_item_field_lines",
              "render_item_particles"):
        assert t in types, f"缺失节点类型: {t}"
    assert domains["dipole"] == "field"
    assert domains["boris_integrator"] == "particle"
    assert domains["render_item_particles"] == "render"
    print(f"C1 注册表:{len(types)} 类型,三域齐备 ✓")

    # C2 图加载(类型校验 + 拓扑环检查)
    g = Graph(reg, None)
    with open(PRESET, encoding="utf-8") as f:
        doc = json.load(f)
    g.load_json(doc)
    assert len(g.nodes) == 8 and len(g.inputs_map) == 7
    print(f"C2 图加载:{len(g.nodes)} 节点 {len(g.inputs_map)} 边,拓扑校验 ✓")

    # C3 三域列带布局(场左 → 粒子中 → 渲染右,渲染域垂直链)
    xs_field = [g._pos[n][0] for n in ("dip", "ob")]
    xs_particle = [g._pos[n][0] for n in ("pe", "bi", "oe")]
    xs_render = [g._pos[n][0] for n in ("rp", "rfl", "rpt")]
    assert max(xs_field) < min(xs_particle) < min(xs_render), \
        (xs_field, xs_particle, xs_render)
    y_render = [g._pos[n][1] for n in ("rp", "rfl", "rpt")]
    y_particle = [g._pos[n][1] for n in ("pe", "bi", "oe")]
    assert y_render == sorted(y_render) and y_particle == sorted(y_particle)
    print("C3 三域列带布局(场左→粒子中→渲染右,链垂直有序)✓")

    # C4 场域烘焙:偶极场量级 + r^-3 衰减 + 全有限
    baked = g.bake(["B"])["B"]
    xs = np.asarray(baked["xs"]); ys = np.asarray(baked["ys"])
    zs = np.asarray(baked["zs"])
    bx = np.asarray(baked["bx"]).reshape(len(xs), len(ys), len(zs))
    by = np.asarray(baked["by"]).reshape(len(xs), len(ys), len(zs))
    bz = np.asarray(baked["bz"]).reshape(len(xs), len(ys), len(zs))
    assert np.all(np.isfinite(bx)) and np.all(np.isfinite(by)) and \
        np.all(np.isfinite(bz))

    def mag_at(pt):
        i = np.argmin(np.abs(xs - pt[0]))
        j = np.argmin(np.abs(ys - pt[1]))
        k = np.argmin(np.abs(zs - pt[2]))
        return float(np.sqrt(bx[i, j, k] ** 2 + by[i, j, k] ** 2 +
                             bz[i, j, k] ** 2))

    b1, b2, b3 = mag_at((1, 0, 0)), mag_at((2, 0, 0)), mag_at((3, 0, 0))
    assert 1000.0 <= b3 <= 2000.0, f"r=3 处 |B|={b3:.0f} nT 超出偶极量级"
    ratio = b1 / b2
    assert 7.5 <= ratio <= 8.5, f"r^-3 衰减比 {ratio:.2f} ≠ 8"
    print(f"C4 场烘焙:|B|(1Re)={b1:.0f} |B|(2Re)={b2:.0f} |B|(3Re)={b3:.0f} nT,"
          f"衰减比 {ratio:.2f}≈8 ✓")

    # C5 粒子域执行计划
    plan = g.particle_plan()
    assert [o["kind"] for o in plan["ops"]] == ["emitter", "step", "encode"], \
        [o["kind"] for o in plan["ops"]]
    assert plan["ops"][1]["kernel"] == "boris"
    assert plan["ops"][1]["slots"]["b"] == "B"
    assert plan["ops"][1]["slots"]["e"] is None
    assert plan["slow_path"] is False
    print("C5 粒子计划:emitter→step(boris,B槽)→encode ✓")

    # C6 渲染域绑定表
    binds = {b["type"]: b for b in g.render_bindings()}
    assert binds["render_item_field_lines"]["inputs"]["data"] == ["ob", "out"]
    assert "data" not in binds["render_item_particles"]["inputs"]
    print("C6 渲染绑定:场线←B 槽,粒子项无数据边 ✓")

    # C7 JSON 往返位级一致(重烘焙逐位相同)
    g2 = Graph(reg, None)
    g2.load_json(g.to_json())
    baked2 = g2.bake(["B"])["B"]
    assert baked2["bx"] == baked["bx"] and baked2["by"] == baked["by"] and \
        baked2["bz"] == baked["bz"]
    assert g2.particle_plan()["ops"] == plan["ops"]
    print("C7 JSON 往返:重烘焙逐位一致,计划等价 ✓")

    print("A 部分(纯引擎)全部通过 ✅")


# ================= B 部分:服务器运行时 =================

async def wait_for(ws, pred, timeout=120):
    while True:
        frame = await asyncio.wait_for(ws.recv(), timeout)
        if isinstance(frame, (bytes, bytearray)):
            view = bytes(frame)
            hlen = struct.unpack("<I", view[:4])[0]
            header = json.loads(view[4:4 + hlen].decode("utf-8"))
            if pred(("bin", header)):
                return view, header
            continue
        m = json.loads(frame)
        if pred((m.get("type"), m)):
            return m, m


async def part_b():
    import websockets
    with open(PRESET, encoding="utf-8") as f:
        preset = json.load(f)

    async with websockets.connect("ws://127.0.0.1:8001/ws", max_size=None) as ws:
        # C8 初始连接
        m, _ = await wait_for(ws, lambda t: t[0] == "init_config", 10)
        print(f"C8 连接:init_config(version={m['version']})✓")

        # C9 上传最简预设 → 烘焙完成 → 几何帧(场线)
        await ws.send(json.dumps({"type": "graph.upload", "graph": preset}))
        await wait_for(ws, lambda t: t[0] == "bake_progress"
                        and t[1]["state"] == "done")
        view, hdr = await wait_for(ws, lambda t: t[0] == "bin"
                                   and t[1].get("type") == "geom")
        assert hdr["kind"] == "field_lines" and hdr["node"] == "rfl"
        assert hdr["slot"] == "B" and hdr["count"] > 0
        off = 4 + struct.unpack("<I", view[:4])[0]
        n_lines = 0
        while off < len(view):
            n = struct.unpack("<H", view[off + 2:off + 4])[0]
            off += 4 + n * 12
            n_lines += 1
        assert n_lines == hdr["count"] and off == len(view)
        print(f"C9 烘焙→几何帧:场线 {hdr['count']} 条(逐线结构校验)✓")

        # C10 粒子帧:21B 编码 + 仿真确实在推进(两帧二进制不同)
        v1, h1 = await wait_for(ws, lambda t: t[0] == "bin"
                                and t[1].get("type") == "s")
        hlen = struct.unpack("<I", v1[:4])[0]
        assert len(v1) == 4 + hlen + h1["n"] * 21  # 长度前缀 + 头 JSON + 负载
        v2, h2 = await wait_for(ws, lambda t: t[0] == "bin"
                                and t[1].get("type") == "s")
        hlen2 = struct.unpack("<I", v2[:4])[0]
        assert v1[4 + hlen:] != v2[4 + hlen2:], "两帧粒子载荷应不同(仿真推进)"
        print(f"C10 粒子帧:n={h1['n']},21B/粒子,连续帧载荷变化(推进中)✓")

        # C11 参数热更新(dt 0.01 → 0.02)
        await ws.send(json.dumps({"type": "node.param", "node": "bi",
                                  "name": "dt", "value": 0.02}))
        await wait_for(ws, lambda t: t[0] == "bake_progress"
                        and t[1]["state"] == "done")
        _, h3 = await wait_for(ws, lambda t: t[0] == "bin"
                               and t[1].get("type") == "s"
                               and t[1]["v"] > h2["v"])
        print(f"C11 参数热更新:dt→0.02,图版本 {h2['v']}→{h3['v']},帧继续 ✓")

        # C12 respawn 受理
        await ws.send(json.dumps({"type": "respawn"}))
        await wait_for(ws, lambda t: t[0] == "bin"
                       and t[1].get("type") == "s")
        print("C12 respawn:粒子重生后帧继续 ✓")

        # C13 插件热加载:丢文件 → 注册表刷新广播 → 新类型可用
        # (注意:下划线开头的 .py 被 registry 视为私有模块,故意跳过)
        plugin = os.path.join(ROOT, "user_nodes", "comp_test_plugin.py")
        try:
            with open(plugin, "w", encoding="utf-8") as f:
                f.write(
                    "from engine import register_node, Node, Param\n"
                    "@register_node(type='comp_test_node', name='组件测试节点',\n"
                    "    category='测试', outputs={'out': 'scalar'},\n"
                    "    params={'v': Param('scalar', default=1.0)})\n"
                    "class CompTestNode(Node):\n"
                    "    def compute(self):\n"
                    "        return {'out': self.params['v']}\n")
            m, _ = await wait_for(ws, lambda t: t[0] == "registry", 15)
            names = [s["type"] for s in m["types"]]
            assert "comp_test_node" in names
            print("C13 插件热加载:丢文件 → 注册表刷新(comp_test_node)✓")
        finally:
            os.remove(plugin)

        print("B 部分(服务器运行时)全部通过 ✅")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", action="store_true", help="同时跑服务器运行时部分")
    args = ap.parse_args()
    part_a()
    if args.ws:
        asyncio.run(part_b())
    print("\n组件测试全部通过 ✅")
