"""持续创生端到端测试(#35):死亡粒子逐帧重生 vs 一次性播撒衰减。

背景(用户反馈):"粒子消失了不会持续创生" —— 死亡粒子(status=1 沉降 /
2 越界)以前不会重生,Van Allen 这类损失锥明显的场景几秒内就从 6000 掉到
~1900 再也不涨。现在发射器有 `respawn`(默认 True),计划里生成 respawn
算子,C++ 在**所有步进之后**逐帧重生。

本测试验证:
  1. respawn=true:长时间跑下去存活率保持 ~100%
  2. respawn=false:编译期告警 respawn_off,且死伤过半时**运行期**告警
     population_decaying(用户不用猜为什么粒子在消失)
  3. 切回 respawn=true:告警消失、存活率回升

注意:每次采样都用**新连接**。旧连接会积压大粒子帧(6000×21B≈126KB/帧),
让"当前状态"看起来停留在几十秒前 —— 这正是客户端信箱合并(#35)要解决的
现象,测试里也顺带规避。

前置:服务端已启动(默认端口 8001)
运行: python tests/test_ws_respawn.py
"""
import asyncio
import functools
import json
import os
import struct
import sys
import time
import urllib.request

import websockets

print = functools.partial(print, flush=True)
API = "http://127.0.0.1:8001/api"
WS = "ws://127.0.0.1:8001/ws"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESET = os.path.join(ROOT, "graphs", "preset_van_allen.json")


async def recv_until(ws, pred, timeout=150):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            f = await asyncio.wait_for(ws.recv(), 5)
        except (asyncio.TimeoutError, TimeoutError):
            continue
        if isinstance(f, (bytes, bytearray)):
            v = bytes(f)
            hl = struct.unpack("<I", v[:4])[0]
            m = ("bin", json.loads(v[4:4 + hl].decode("utf-8")), v)
        else:
            m = ("txt", json.loads(f), None)
        if pred(m):
            return m
    return None


def alive_ratio(v, n, sample=2000):
    off = 4 + struct.unpack("<I", v[:4])[0]
    step = max(1, n // sample)
    a = tot = 0
    for i in range(0, n, step):
        tot += 1
        if v[off + 21 * i + 16] == 0:
            a += 1
    return a / max(1, tot)


async def snapshot(label):
    """新连接采样:缓存的 plan_status + 最新粒子帧(不带积压)。"""
    async with websockets.connect(WS, max_size=None) as ws:
        plan, frame = None, None
        t0 = time.monotonic()
        while time.monotonic() - t0 < 10:
            try:
                f = await asyncio.wait_for(ws.recv(), 2)
            except (asyncio.TimeoutError, TimeoutError):
                continue
            if isinstance(f, (bytes, bytearray)):
                v = bytes(f)
                hl = struct.unpack("<I", v[:4])[0]
                h = json.loads(v[4:4 + hl].decode("utf-8"))
                if h.get("type") == "s":
                    frame = (h, v)
                continue
            m = json.loads(f)
            if m.get("type") == "plan_status":
                plan = m
        codes = [w["code"] for w in (plan or {}).get("warnings", [])]
        ratio = alive_ratio(frame[1], frame[0]["n"]) if frame else float("nan")
        print("   %-14s t=%7.1fs 存活 %5.1f%%  respawn=%s 告警=%s"
              % (label, (frame[0].get("t", 0) if frame else 0), 100 * ratio,
                 (plan or {}).get("respawn"), codes))
        return ratio, codes


async def upload(doc, expect_warn=None):
    async with websockets.connect(WS, max_size=None) as ws:
        await ws.send(json.dumps({"type": "graph.upload", "graph": doc}))
        await recv_until(ws, lambda m: m[1].get("type") == "bake_progress"
                         and m[1].get("state") == "done", 180)


async def main():
    with open(PRESET, encoding="utf-8") as f:
        doc = json.load(f)
    off = json.loads(json.dumps(doc))
    for n in off["nodes"]:
        if n["id"] == "pe":
            n["params"]["respawn"] = False
        if n["id"] == "bi":
            # 测试只关心"死伤过半是否告警",让仿真时间快进(substeps 2→20),
            # 否则要等服务器跑满几十秒仿真时间,负载一高就等不到
            n["params"]["substeps"] = 20

    # ---- 1) respawn=false:编译期告警 + 运行期衰减 --------------------
    print("=== respawn=false(一次性播撒,应衰减并告警)")
    await upload(off)
    ratio0, codes0 = await snapshot("刚切换")
    assert "respawn_off" in codes0, f"缺 respawn_off 编译期告警: {codes0}"
    print("   ✓ 编译期告警 respawn_off(提前说清会衰减)")
    decaying = False
    ratio_end = ratio0
    for i in range(8):
        await asyncio.sleep(12)
        ratio_end, codes = await snapshot(f"第 {i + 1} 次")
        if "population_decaying" in codes:
            decaying = True
            break
    assert decaying, "死伤过半后未出现 population_decaying 运行期告警"
    assert ratio_end < 0.6, f"死亡率未过半但已报衰减: {ratio_end:.2f}"
    print(f"   ✓ 运行期告警 population_decaying(存活 {100 * ratio_end:.1f}%)")

    # ---- 2) respawn=true:回升到满员且告警消失 ------------------------
    print("=== respawn=true(持续创生)")
    await upload(doc)
    await asyncio.sleep(6)
    best = 0.0
    for i in range(4):
        r, codes = await snapshot(f"恢复 {i + 1}")
        best = max(best, r)
        assert "population_decaying" not in codes, f"重生已开但仍有衰减告警: {codes}"
        assert "respawn_off" not in codes, f"重生已开但仍有 respawn_off: {codes}"
        await asyncio.sleep(8)
    assert best > 0.95, f"持续创生后存活率未回升: {best:.2f}"
    print(f"   ✓ 存活率回升到 {100 * best:.1f}%,衰减告警消失")

    print("\n持续创生端到端测试全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
