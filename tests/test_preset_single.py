"""单粒子预设(偶极子)端到端:加载 → 单粒子帧 → 重生确定性。

前置:服务端已启动
  mf_server --root . --port 8001
运行: python tests/test_preset_single.py
"""
import asyncio
import functools
import json
import math
import os
import struct

import websockets

print = functools.partial(print, flush=True)
HOST = "ws://127.0.0.1:8001/ws"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESET = os.path.join(ROOT, "graphs", "preset_dipole_single.json")


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


def decode_head(view):
    hlen = struct.unpack("<I", view[:4])[0]
    hdr = json.loads(view[4:4 + hlen].decode("utf-8"))
    off = 4 + hlen
    pid, fx, fy, fz = struct.unpack("<i f f f", view[off:off + 16])
    st = view[off + 16]
    color = struct.unpack("<I", view[off + 17:off + 21])[0]
    x, y, z = fx, -fz, fy          # 场景 → GSM(与帧协议互逆)
    return hdr, pid, (x, y, z), st, color


async def main():
    with open(PRESET, encoding="utf-8") as f:
        preset = json.load(f)
    r_inj = next(n for n in preset["nodes"]
                 if n["type"] == "particle_injection")["params"]["r"]

    async with websockets.connect(HOST, max_size=None) as ws:
        await wait_for(ws, lambda t: t[0] == "init_config", 10)
        print("✓ 连接")
        await ws.send(json.dumps({"type": "graph.upload", "graph": preset}))
        await wait_for(ws, lambda t: t[0] == "bake_progress"
                        and t[1]["state"] == "done")
        print("✓ 预设加载 + 烘焙完成")

        hdr, view = await wait_for(ws, lambda t: t[0] == "s" and t[1]["n"] == 1)
        assert hdr["n"] == 1, hdr
        _, pid, pos, st, color = decode_head(view)
        r = math.sqrt(sum(c * c for c in pos))
        print(f"✓ 单粒子帧: id={pid} r={r:.3f} Re status={st} #{color:06x}")
        assert st == 0, f"应存活: status={st}"
        assert abs(r - r_inj) < 0.6, f"应生成在 r≈{r_inj}: r={r:.3f}"
        assert color == 0xff5555, f"物种链首(质子)应为 #ff5555: #{color:06x}"

        # 连续多帧:俯仰角 70° → 磁镜捕获(存活且半径有界)
        rs = [r]
        for _ in range(6):
            _, _, p, s2, _ = decode_head(
                (await wait_for(ws, lambda t: t[0] == "s"))[1])
            assert s2 == 0, f"俯仰角 70° 应被捕获(实测 status={s2})"
            rs.append(math.sqrt(sum(c * c for c in p)))
        print(f"  半径采样: {['%.2f' % v for v in rs]}")
        assert max(rs) < 15.0, f"应被磁场捕获(半径应有界): max={max(rs):.2f}"

        # 重生确定性:同 id 序列位置可复现(回到注入点附近)
        await ws.send(json.dumps({"type": "respawn"}))
        _, _, p2, s3, _ = decode_head(
            (await wait_for(ws, lambda t: t[0] == "s"))[1])
        r2 = math.sqrt(sum(c * c for c in p2))
        assert s3 == 0 and abs(r2 - r_inj) < 0.6, f"重生应回到 r≈{r_inj}: {r2:.3f}"
        print(f"✓ 重生确定性:r={r2:.3f} Re")

        # 复位默认图(不留调试状态)
        with open(os.path.join(ROOT, "graphs", "default_graph.json"),
                  encoding="utf-8") as f:
            await ws.send(json.dumps({"type": "graph.upload", "graph": json.load(f)}))
        await wait_for(ws, lambda t: t[0] == "bake_progress" and t[1]["state"] == "done")
        print("✓ 已复位默认图")
        print("单粒子预设测试全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
