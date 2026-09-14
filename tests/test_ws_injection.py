"""单粒子注入端到端:图内注入节点 → 计划 → 确定性单粒子帧。

前置:服务端已启动
  mf_server --root . --port 8001
运行: python tests/test_ws_injection.py
"""
import asyncio
import functools
import json
import math
import struct

import websockets

print = functools.partial(print, flush=True)
HOST = "ws://127.0.0.1:8001/ws"
R0 = 6.6          # 注入地心距(Re)
LON = 0.0         # 经度 → GSM (r,0,0)


def inj_graph(pos_mode="rll", vel_mode="vpitch", pitch=90.0, r=R0):
    return {
        "version": 1,
        "lattice": {"preset": "tiny"},
        "nodes": [
            {"id": "dip", "type": "dipole", "input_defaults": {"ps": 0.5}},
            {"id": "ob", "type": "output_slot", "params": {"slot": "B"}},
            {"id": "inj", "type": "particle_injection",
             "params": {"pos_mode": pos_mode, "r": r, "lat": 0.0, "lon": LON,
                        "x": r, "y": 0.0, "z": 0.0,
                        "vel_mode": vel_mode, "v": 400.0, "pitch": pitch,
                        "phase": 0.0, "vx": 0.0, "vy": 0.0, "vz": 400.0}},
            {"id": "sp", "type": "particle_species", "params": {"preset": "proton"}},
            {"id": "pe", "type": "particle_emitter",
             "params": {"count": 1, "max_range": 15.0}},
            {"id": "bi", "type": "boris_integrator",
             "params": {"dt": 0.01, "substeps": 5, "max_range": 15.0}},
            {"id": "oe", "type": "output_encoder"},
        ],
        "edges": [
            {"from": ["dip", "field"], "to": ["ob", "field"]},
            {"from": ["inj", "spec"], "to": ["pe", "init"]},
            {"from": ["sp", "types"], "to": ["pe", "types"]},
            {"from": ["ob", "out"], "to": ["bi", "b"]},
            {"from": ["pe", "next"], "to": ["bi", "prev"]},
            {"from": ["bi", "next"], "to": ["oe", "prev"]},
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
            if header.get("type") == "s" and pred(("s", header, view)):
                return header, view
            continue
        m = json.loads(frame)
        if pred((m.get("type"), m)):
            return m, None


def decode_one(view):
    """解码单粒子帧:GSM (x,y,z)(编码时做过 Three 重映射,这里还原)。"""
    hlen = struct.unpack("<I", view[:4])[0]
    hdr = json.loads(view[4:4 + hlen].decode("utf-8"))
    off = 4 + hlen
    pid, fx, fy, fz = struct.unpack("<i f f f", view[off:off + 16])
    status = view[off + 16]
    color = struct.unpack("<I", view[off + 17:off + 21])[0]
    # 编码约定 (x,y,z)_gsm → (x, z, -y)_scene
    x, y, z = fx, -fz, fy
    return hdr, pid, (x, y, z), status, color


async def part_a():
    async with websockets.connect(HOST, max_size=None) as ws:
        await wait_for(ws, lambda t: t[0] == "init_config", 10)
        print("✓ 连接")

        # 1) 注入 → 帧内仅 1 个粒子
        await ws.send(json.dumps({"type": "graph.upload", "graph": inj_graph()}))
        await wait_for(ws, lambda t: t[0] == "bake_progress"
                        and t[1]["state"] == "done")
        hdr, view = await wait_for(ws, lambda t: t[0] == "s" and t[1]["n"] == 1)
        assert hdr["n"] == 1, hdr
        print("✓ count=1 生效:帧内 1 个粒子")

        h2, pid, pos, status, color = decode_one(view)
        r = math.sqrt(sum(c * c for c in pos))
        print(f"  粒子: id={pid} pos=({pos[0]:.3f},{pos[1]:.3f},{pos[2]:.3f}) "
              f"r={r:.3f} Re status={status} color=#{color:06x}")
        assert status == 0, f"单粒子应存活,status={status}"
        assert abs(r - R0) < 0.5, f"应生成在 r≈{R0} Re 附近(实测 {r:.3f})"
        assert color == 0xff5555, f"物种链首(质子)颜色应为 #ff5555,实测 #{color:06x}"
        print("✓ 生成位置/物种/颜色均符合注入 + 物种链声明")

        # 2) 俯仰角 90°:磁镜捕获 → 半径在多次采样中保持在同一 L 壳附近
        radii = []
        for _ in range(5):
            _, _, p, st, _ = decode_one(
                (await wait_for(ws, lambda t: t[0] == "s"))[1])
            assert st == 0, "俯仰角 90° 的粒子应被磁场捕获(不沉降/不出界)"
            radii.append(math.sqrt(sum(c * c for c in p)))
        spread = max(radii) - min(radii)
        print(f"  5 帧半径采样: {['%.3f' % v for v in radii]}, 波动 {spread:.4f} Re")
        assert spread < 0.05, "磁镜捕获:半径应稳定(90° 俯仰角)"
        print("✓ 俯仰角 90° → 磁镜捕获(半径稳定)")

        # 3) respawn 后仍为 1 个粒子且位置回到注入点附近(确定性)
        await ws.send(json.dumps({"type": "respawn"}))
        _, _, p2, st2, _ = decode_one(
            (await wait_for(ws, lambda t: t[0] == "s"))[1])
        r2 = math.sqrt(sum(c * c for c in p2))
        assert st2 == 0 and abs(r2 - R0) < 0.5, f"重生后应回到 r≈{R0},实测 {r2:.3f}"
        print(f"✓ respawn → 重新注入同一初条件(r={r2:.3f} Re)")

        # 4) 切换到 vxyz 模式(沿 B 方向的束流)→ 仍 1 粒子、有限
        await ws.send(json.dumps({"type": "graph.upload",
                                  "graph": inj_graph(vel_mode="vxyz")}))
        await wait_for(ws, lambda t: t[0] == "bake_progress"
                        and t[1]["state"] == "done")
        _, _, p3, st3, _ = decode_one(
            (await wait_for(ws, lambda t: t[0] == "s" and t[1]["n"] == 1))[1])
        finite = all(math.isfinite(c) for c in p3)
        assert finite and st3 == 0, f"vxyz 模式应有限且存活: {p3} status={st3}"
        print(f"✓ vxyz 模式:pos=({p3[0]:.3f},{p3[1]:.3f},{p3[2]:.3f}) 存活")

        # 5) 复位默认图
        import os
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "graphs", "default_graph.json"), encoding="utf-8") as f:
            doc = json.load(f)
        await ws.send(json.dumps({"type": "graph.upload", "graph": doc}))
        await wait_for(ws, lambda t: t[0] == "bake_progress" and t[1]["state"] == "done")
        print("✓ 已复位默认图")
        print("单粒子注入端到端测试全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(part_a())
