"""重启后快速冒烟(几十秒):预设发现 → 多场对照 → 粒子帧 → 场源广播 → 衰减告警。

比全套回归快得多,用来在"刚重启服务器"时确认关键链路是通的。
用法:python tests/smoke_quick.py(需服务器已在 8001 运行)

覆盖:
  1. /api/presets 能发现预设(引导页卡片)
  2. 多场对照:一张图 偶极→B + A2000→B2 → **两个几何帧各自产出**(#40 多槽位)
  3. 粒子帧到达(n>0)
  4. plan_status 带 b_slot/b_source(界面"场源"行,多场并存时指认粒子用哪个场)
  5. 关掉持续创生 → 死伤过半出现 population_decaying 运行期告警(用 substeps 加速仿真)
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
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "http://127.0.0.1:8001/api"
WS = "ws://127.0.0.1:8001/ws"


async def recv_until(ws, pred, timeout=60):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            f = await asyncio.wait_for(ws.recv(), 3)
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


def load(name):
    with open(os.path.join(ROOT, "graphs", name), encoding="utf-8") as f:
        return json.load(f)


async def test_multi_field():
    with urllib.request.urlopen(API + "/presets", timeout=10) as r:
        cards = json.load(r)
    ids = [c["id"] for c in cards]
    assert "compare_fields" in ids and "paraboloid" in ids, ids
    print("✓ 预设发现:%d 张卡片(含 %s)" % (len(cards), ", ".join(ids[:3]) + " …"))

    doc = load("preset_compare_fields.json")
    async with websockets.connect(WS, max_size=None) as ws:
        await recv_until(ws, lambda m: m[1].get("type") == "init_config", 20)
        await ws.send(json.dumps({"type": "graph.upload", "graph": doc}))
        st = await recv_until(ws, lambda m: m[1].get("type") == "plan_status"
                              and m[1].get("b_slot"), 60)
        assert st, "未收到带 b_slot 的 plan_status"
        print("✓ plan_status 场源广播:b_slot=%s b_source=%s"
              % (st[1]["b_slot"], st[1].get("b_source")))
        bk = await recv_until(ws, lambda m: m[1].get("type") == "bake_progress"
                              and m[1].get("state") in ("done", "error"), 90)
        assert bk and bk[1]["state"] == "done", bk
        frames, n = {}, 0
        t0 = time.monotonic()
        while time.monotonic() - t0 < 25 and (len(frames) < 2 or n == 0):
            try:
                f = await asyncio.wait_for(ws.recv(), 3)
            except (asyncio.TimeoutError, TimeoutError):
                continue
            if isinstance(f, (bytes, bytearray)):
                v = bytes(f)
                hl = struct.unpack("<I", v[:4])[0]
                h = json.loads(v[4:4 + hl].decode("utf-8"))
                if h.get("type") == "geom":
                    frames[h.get("node")] = h.get("slot")
                elif h.get("type") == "s":
                    n = h.get("n", 0)
        assert len(frames) == 2, f"应有两个几何帧(两个场线项),实得 {frames}"
        assert sorted(frames.values()) == ["B", "B2"], frames
        assert n > 0, "未收到粒子帧"
        print("✓ 多场对照:两个几何帧各自产出 %s;粒子帧 n=%d(只走 b_slot=%s)"
              % (frames, n, st[1]["b_slot"]))


async def test_decay_warning(timeout=75):
    doc = load("preset_van_allen.json")
    for nd in doc["nodes"]:
        if nd["id"] == "pe":
            nd["params"]["respawn"] = False
        if nd["id"] == "bi":
            nd["params"]["substeps"] = 20      # 加速仿真时间,免得等太久
    async with websockets.connect(WS, max_size=None) as ws:
        await ws.send(json.dumps({"type": "graph.upload", "graph": doc}))
        st = await recv_until(ws, lambda m: m[1].get("type") == "plan_status"
                              and "respawn_off" in [w["code"] for w in
                                                    (m[1].get("warnings") or [])], 60)
        assert st, "缺 respawn_off 编译期告警"
        print("✓ 关闭持续创生 → 编译期告警 respawn_off")
        t0 = time.monotonic()
        best = 1.0
        while time.monotonic() - t0 < timeout:
            r = await recv_until(ws, lambda m: m[1].get("type") == "s", 5)
            if r:
                best = min(best, alive_ratio(r[2], r[1]["n"]))
            p = await recv_until(ws, lambda m: m[1].get("type") == "plan_status"
                                 and "population_decaying" in
                                 [w["code"] for w in (m[1].get("warnings") or [])], 1)
            if p:
                print("✓ 运行期告警 population_decaying(最低存活 %.0f%%)"
                      % (100 * best))
                return
        raise AssertionError("未在 %ds 内看到 population_decaying(最低存活 %.0f%%)"
                             % (timeout, 100 * best))


async def main():
    await test_multi_field()
    await test_decay_warning()
    print("\n快速冒烟全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
