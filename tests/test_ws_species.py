"""粒子物种端到端:图内声明 e/p/α → 发射器按物种生成 → 帧颜色验证。

前置:服务端已启动(默认图含物种节点,或任意图)
  mf_server --root . --port 8001
运行: python tests/test_ws_species.py
"""
import asyncio
import functools
import json
import struct

import websockets

print = functools.partial(print, flush=True)

HOST = "ws://127.0.0.1:8001/ws"

# 三种预设颜色(与 nodes/particle_nodes.py _SPECIES_PRESETS 一致)
C_ELECTRON = 0x5599ff
C_PROTON = 0xff5555
C_ALPHA = 0xffaa33


def species_rows(alpha_enabled, proton_mass=1.0):
    return [
        {"preset": "electron", "name": "电子", "q": -1.0, "mass": 1 / 1836,
         "v_mult": 1.0, "weight": 1.0, "color": "#5599ff", "enabled": True},
        {"preset": "proton", "name": "质子", "q": 1.0, "mass": proton_mass,
         "v_mult": 1.0, "weight": 1.0, "color": "#ff5555", "enabled": True},
        {"preset": "alpha", "name": "α粒子", "q": 2.0, "mass": 4.0,
         "v_mult": 1.0, "weight": 1.0, "color": "#ffaa33",
         "enabled": alpha_enabled},
    ]


def species_graph(alpha_enabled, proton_mass=1.0):
    """#30:物种用「粒子种群」行表(接线决定归属);α 行的 enabled 可切换。"""
    return {
        "version": 1,
        "lattice": {"preset": "tiny"},
        "nodes": [
            {"id": "dip", "type": "dipole", "input_defaults": {"ps": 0.5}},
            {"id": "ob", "type": "output_slot", "params": {"slot": "B"}},
            {"id": "pop", "type": "particle_population",
             "params": {"order": 20,
                        "rows": species_rows(alpha_enabled, proton_mass)}},
            {"id": "pe", "type": "particle_emitter",
             "params": {"mode": 1, "v_base": 500.0, "max_range": 15.0}},
            {"id": "bi", "type": "boris_integrator",
             "params": {"dt": 0.01, "substeps": 5, "max_range": 15.0}},
            {"id": "oe", "type": "output_encoder"},
        ],
        "edges": [
            {"from": ["dip", "field"], "to": ["ob", "field"]},
            {"from": ["ob", "out"], "to": ["bi", "b"]},
            {"from": ["pop", "types"], "to": ["pe", "types"]},
        ],
        "outputs": {},
    }


async def wait_for(ws, pred, timeout=120):
    while True:
        frame = await asyncio.wait_for(ws.recv(), timeout)
        if isinstance(frame, (bytes, bytearray)):
            view = bytes(frame)
            hlen = struct.unpack("<I", view[:4])[0]
            header = json.loads(view[4:4 + hlen].decode("utf-8"))
            if header.get("type") == "s":
                if pred(("s", header, view)):
                    return header, view
            continue
        m = json.loads(frame)
        if pred((m.get("type"), m)):
            return m, None


def frame_colors(view):
    hlen = struct.unpack("<I", view[:4])[0]
    n = json.loads(view[4:4 + hlen].decode("utf-8"))["n"]
    colors = set()
    off = 4 + hlen
    for _ in range(n):
        colors.add(struct.unpack("<I", view[off + 17:off + 21])[0])
        off += 21
    return colors


async def restore_default(ws):
    """测试复位:恢复默认图(否则服务器停在无渲染链的测试图,视口空屏)。"""
    import os
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "graphs", "default_graph.json"), encoding="utf-8") as f:
        doc = json.load(f)
    await ws.send(json.dumps({"type": "graph.upload", "graph": doc}))
    await wait_for(ws, lambda t: t[0] == "bake_progress" and t[1]["state"] == "done")


async def main():
    async with websockets.connect(HOST, max_size=None) as ws:
        await wait_for(ws, lambda t: t[0] == "init_config", 10)
        print("✓ 连接")

        # 1) α 禁用:e/p 双色
        await ws.send(json.dumps({"type": "graph.upload",
                                  "graph": species_graph(False)}))
        await wait_for(ws, lambda t: t[0] == "bake_progress"
                        and t[1]["state"] == "done")
        hdr, view = await wait_for(ws, lambda t: t[0] == "s")
        colors = frame_colors(view)
        assert colors == {C_ELECTRON, C_PROTON}, \
            f"启用物种应为 e/p 双色,实际 {[hex(c) for c in colors]}"
        print(f"✓ α 禁用:帧内 {hdr['n']} 粒子,颜色 = 电子+质子")

        # 2) 启用 α(整表推送:行表是一个参数值)→ 三色
        await ws.send(json.dumps({"type": "node.param", "node": "pop",
                                  "name": "rows",
                                  "value": species_rows(True)}))
        await wait_for(ws, lambda t: t[0] == "bake_progress"
                        and t[1]["state"] == "done")
        hdr2, view2 = await wait_for(ws, lambda t: t[0] == "s"
                                     and t[1]["v"] > hdr["v"])
        colors2 = frame_colors(view2)
        assert colors2 == {C_ELECTRON, C_PROTON, C_ALPHA}, \
            f"启用 α 后应为三色,实际 {[hex(c) for c in colors2]}"
        print("✓ α 启用:帧内三色 = 电子+质子+α粒子")

        # 3) 编辑行内物理量(质子质量 → 2.0)仍正常出帧
        await ws.send(json.dumps({"type": "node.param", "node": "pop",
                                  "name": "rows",
                                  "value": species_rows(True, proton_mass=2.0)}))
        await wait_for(ws, lambda t: t[0] == "bake_progress"
                        and t[1]["state"] == "done")
        await wait_for(ws, lambda t: t[0] == "s" and t[1]["v"] > hdr2["v"])
        print("✓ 行内参数编辑后帧继续")

        # 4) 复位默认图,不留空屏状态
        await restore_default(ws)
        print("✓ 已复位默认图")
        print("粒子物种端到端测试全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
