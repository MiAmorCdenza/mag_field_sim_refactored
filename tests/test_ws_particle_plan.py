"""粒子域 L1 端到端测试:粒子子图 → 执行计划 → 原生管线运行。

前置:服务端已启动
  mf_server --root . --port 8001 --particles 5000
运行: python tests/test_ws_particle_plan.py
"""
import asyncio
import functools
import json
import struct

import websockets

print = functools.partial(print, flush=True)

HOST = "ws://127.0.0.1:8001/ws"


def plan_graph(integrator="boris_integrator"):
    return {
        "version": 1,
        "lattice": {"preset": "tiny"},
        "nodes": [
            {"id": "dip", "type": "dipole", "input_defaults": {"ps": 0.5}},
            {"id": "ob", "type": "output_slot", "params": {"slot": "B"}},
            {"id": "pe", "type": "particle_emitter",
             "params": {"mode": 1, "v_base": 500.0, "max_range": 15.0}},
            {"id": "bi", "type": integrator,
             "params": {"dt": 0.01, "substeps": 5, "max_range": 15.0}},
            {"id": "oe", "type": "output_encoder"},
        ],
        "edges": [
            {"from": ["dip", "field"], "to": ["ob", "field"]},
            {"from": ["ob", "out"], "to": ["bi", "b"]},
            {"from": ["pe", "next"], "to": ["bi", "prev"]},
            {"from": ["bi", "next"], "to": ["oe", "prev"]},
        ],
        "outputs": {},
    }


async def wait_for(ws, pred, timeout=120):
    """等待满足条件的帧;跳过二进制粒子帧(由 pred 决定)。"""
    while True:
        frame = await asyncio.wait_for(ws.recv(), timeout)
        if isinstance(frame, (bytes, bytearray)):
            view = bytes(frame)
            hlen = struct.unpack("<I", view[:4])[0]
            header = json.loads(view[4:4 + hlen].decode("utf-8"))
            if header.get("type") == "s":
                body_len = len(view) - 4 - hlen
                assert body_len == header["n"] * 21, \
                    f"粒子帧长度错误: {body_len} != {header['n']}×21"
                if pred(("s", header)):
                    return header
            continue
        m = json.loads(frame)
        if pred((m.get("type"), m)):
            return m


async def main():
    async with websockets.connect(HOST, max_size=None) as ws:
        # 1) init_config
        m = await wait_for(ws, lambda t: t[0] == "init_config", 10)
        print("✓ init_config,version=%d" % m["version"])

        # 2) 上传含粒子链的图 → 烘焙完成 + 粒子帧流动(计划已应用)
        await ws.send(json.dumps({"type": "graph.upload",
                                  "graph": plan_graph("boris_integrator")}))
        await wait_for(ws, lambda t: t[0] == "bake_progress" and t[1]["state"] == "done")
        print("✓ 粒子链图上传 → 烘焙完成(Boris 内核)")
        hdr = await wait_for(ws, lambda t: t[0] == "s")
        print(f"✓ 粒子帧流动: n={hdr['n']},v={hdr['v']}(执行计划已驱动原生管线)")

        # 3) 节点参数热更新(积分器 dt 0.01 → 0.02)→ 计划重编译 + 帧继续
        await ws.send(json.dumps({"type": "node.param", "node": "bi",
                                  "name": "dt", "value": 0.02}))
        await wait_for(ws, lambda t: t[0] == "bake_progress" and t[1]["state"] == "done")
        hdr2 = await wait_for(ws, lambda t: t[0] == "s" and t[1]["v"] > hdr["v"])
        print(f"✓ dt 参数热更新 → 图版本 {hdr['v']} → {hdr2['v']},粒子帧继续")

        # 4) 换内核节点类型(Boris → RK4)→ 图上换节点 = 换步进器
        await ws.send(json.dumps({"type": "graph.upload",
                                  "graph": plan_graph("rk4_integrator")}))
        await wait_for(ws, lambda t: t[0] == "bake_progress" and t[1]["state"] == "done")
        hdr3 = await wait_for(ws, lambda t: t[0] == "s" and t[1]["v"] > hdr2["v"])
        print(f"✓ 换内核(Boris → RK4)→ 版本 {hdr2['v']} → {hdr3['v']},粒子帧继续")

        # 5) 换回蛙跳内核再验证一次(四内核中的第三个)
        await ws.send(json.dumps({"type": "graph.upload",
                                  "graph": plan_graph("leapfrog_integrator")}))
        await wait_for(ws, lambda t: t[0] == "bake_progress" and t[1]["state"] == "done")
        hdr4 = await wait_for(ws, lambda t: t[0] == "s" and t[1]["v"] > hdr3["v"])
        print(f"✓ 换内核(RK4 → 蛙跳)→ 版本 {hdr3['v']} → {hdr4['v']},粒子帧继续")

        print("粒子域 L1 端到端测试全部通过 ✅")


if __name__ == "__main__":
    import os
    asyncio.run(main())
    # 复位默认图(否则服务器停在无渲染链的测试图,视口空屏)
    import json
    import websockets as _ws
    _doc = json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "graphs", "default_graph.json"), encoding="utf-8"))

    async def _restore():
        async with _ws.connect("ws://127.0.0.1:8001/ws", max_size=None) as w:
            await w.send(json.dumps({"type": "graph.upload", "graph": _doc}))
            while True:
                f = await asyncio.wait_for(w.recv(), 60)
                if isinstance(f, (bytes, bytearray)):
                    continue
                m = json.loads(f)
                if m.get("type") == "bake_progress" and m.get("state") == "done":
                    return
    asyncio.run(_restore())
    print("已复位默认图")
