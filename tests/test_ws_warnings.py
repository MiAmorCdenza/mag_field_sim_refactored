"""计划诊断端到端:真依赖缺失必须上报成 plan_status.warnings(不能静默)。

覆盖(全部为实测踩过的静默失败):
  1. 删积分器 b 数据线     → step_no_b        (粒子不受磁场力,无提示)
  2. 删编码器节点          → no_encoder       (且粒子帧真的停发)
  3. 删场线渲染项 data 线  → render_no_slot   (视口无场线,无提示)
  4. 恢复基线              → 告警清空
  5. 新连接重放            → 告警可见(事件型消息必须缓存重放)

前置:服务端已启动
  mf_server --root . --port 8001
运行: python tests/test_ws_warnings.py
"""
import asyncio
import copy
import functools
import json
import os
import struct
import time

import websockets

print = functools.partial(print, flush=True)
HOST = "ws://127.0.0.1:8001/ws"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESET = os.path.join(ROOT, "graphs", "preset_dipole_single.json")


async def recv_until(ws, pred, timeout=60):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            frame = await asyncio.wait_for(ws.recv(), 5)
        except (asyncio.TimeoutError, TimeoutError):
            continue
        if isinstance(frame, (bytes, bytearray)):
            view = bytes(frame)
            hlen = struct.unpack("<I", view[:4])[0]
            msg = ("bin", json.loads(view[4:4 + hlen].decode("utf-8")), view)
        else:
            msg = ("txt", json.loads(frame), None)
        if pred(msg):
            return msg
    return None


async def upload(ws, doc, wait_bake=True):
    await ws.send(json.dumps({"type": "graph.upload", "graph": doc}))
    if wait_bake:
        await recv_until(ws, lambda m: m[1].get("type") == "bake_progress"
                         and m[1].get("state") == "done")


async def upload_expect(ws, doc, want_code, timeout=60):
    """上传图并等待告警集合满足期望。

    注意:plan_status 在 bake done **之前**广播(计划先行),所以不能先等
    bake 再等告警 —— 会被吞掉。这里累积收集直到两者都见到。
    """
    await ws.send(json.dumps({"type": "graph.upload", "graph": doc}))
    t0 = time.monotonic()
    last = None
    baked = False
    while time.monotonic() - t0 < timeout:
        try:
            frame = await asyncio.wait_for(ws.recv(), 5)
        except (asyncio.TimeoutError, TimeoutError):
            continue
        if isinstance(frame, (bytes, bytearray)):
            continue
        m = json.loads(frame)
        if m.get("type") == "bake_progress" and m.get("state") == "done":
            baked = True
        elif m.get("type") == "plan_status":
            codes = [w["code"] for w in (m.get("warnings") or [])]
            last = codes
            if (want_code is None and not codes) or (want_code in codes):
                return codes
    raise AssertionError(f"未在 {timeout}s 内见到期望告警 {want_code!r}"
                         f"(baked={baked}, 最近告警={last})")


async def main():
    with open(PRESET, encoding="utf-8") as f:
        preset = json.load(f)

    async with websockets.connect(HOST, max_size=None) as ws:
        await recv_until(ws, lambda m: m[1].get("type") == "init_config", 15)

        # 1) 删 bi.b 数据线 → step_no_b
        d = copy.deepcopy(preset)
        d["edges"] = [e for e in d["edges"]
                      if not (e["to"][0] == "bi" and e["to"][1] == "b")]
        codes = await upload_expect(ws, d, "step_no_b")
        print(f"✓ 删 b 数据线 → 告警 {codes}")

        # 2) 删编码器节点:告警 + 粒子帧停发(节点真生效)
        d = copy.deepcopy(preset)
        d["nodes"] = [n for n in d["nodes"] if n["id"] != "enc"]
        d["edges"] = [e for e in d["edges"]
                      if e["to"][0] != "enc" and e["from"][0] != "enc"]
        codes = await upload_expect(ws, d, "no_encoder")
        assert "no_encoder" in codes, codes
        await recv_until(ws, lambda m: m[1].get("type") == "bake_progress"
                         and m[1].get("state") == "done")
        t0, frames = time.monotonic(), 0
        while time.monotonic() - t0 < 5:
            try:
                f = await asyncio.wait_for(ws.recv(), 2)
            except (asyncio.TimeoutError, TimeoutError):
                continue
            if isinstance(f, (bytes, bytearray)):
                hl = struct.unpack("<I", bytes(f)[:4])[0]
                if json.loads(bytes(f)[4:4 + hl].decode("utf-8")).get("type") == "s":
                    frames += 1
        assert frames == 0, f"无编码器节点时不应发送粒子帧(实测 {frames} 帧)"
        print("✓ 删编码器节点 → no_encoder 告警 + 5 秒 0 粒子帧(节点真生效)")

        # 3) 删场线渲染项 data 线 → render_no_slot
        d = copy.deepcopy(preset)
        d["edges"] = [e for e in d["edges"]
                      if not (e["to"][0] == "rfl" and e["to"][1] == "data")]
        codes = await upload_expect(ws, d, "render_no_slot")
        print("✓ 删场线 data 线 → render_no_slot 告警(视口无场线的真因)")

        # 4) 恢复基线 → 告警清空
        codes = await upload_expect(ws, preset, None)
        assert codes == [], codes
        print("✓ 恢复预设 → 告警清空")

    # 5) 新连接:plan_status 必须重放(否则后连页面看不到告警)
    async with websockets.connect(HOST, max_size=None) as ws2:
        r = await recv_until(ws2, lambda m: m[1].get("type") == "plan_status", 15)
        assert r is not None, "新连接应重放 plan_status"
        print(f"✓ 新连接重放 plan_status(warnings={len(r[1].get('warnings', []))} 条)")

    print("计划诊断端到端测试全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
