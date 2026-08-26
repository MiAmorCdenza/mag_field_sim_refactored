"""高危场景复现:输出槽节点未连线(或上游被删)时上传。
运行: python tests/repro_upload2.py
"""
import asyncio
import json
import urllib.request

import websockets

HOST = "ws://127.0.0.1:8001/ws"


def fetch_graph():
    with urllib.request.urlopen("http://127.0.0.1:8001/api/graph", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


async def recv_text(ws, timeout=30):
    while True:
        frame = await asyncio.wait_for(ws.recv(), timeout)
        if isinstance(frame, (bytes, bytearray)):
            continue
        return json.loads(frame)


async def main():
    doc = fetch_graph()
    # 场景:新增一个未连线的输出槽(默认 slot="B",与已有 ob 重复 → 被跳过)
    doc["nodes"].append({"id": "extra_out", "type": "output_slot",
                         "params": {"slot": "Z"}, "pos": [2000, 2000]})
    # 场景 2:另一个完全未连线的输出槽
    doc["nodes"].append({"id": "bare_out", "type": "output_slot",
                         "params": {"slot": "W"}, "pos": [2200, 2000]})
    upload = {"version": 1, "lattice": {"preset": "tiny"},
              "nodes": doc["nodes"], "edges": doc["edges"],
              "outputs": dict(doc["outputs"])}

    async with websockets.connect(HOST, max_size=None) as ws:
        init = await recv_text(ws, 10)
        assert init["type"] == "init_config"
        await ws.send(json.dumps({"type": "graph.upload", "graph": upload}))
        while True:
            m = await recv_text(ws, 120)
            if m["type"] == "bake_progress":
                print("bake_progress:", m["state"])
                if m["state"] == "error":
                    print("=== 错误详情 ===")
                    print(m.get("note", "")[:1500])
                    return 1
                if m["state"] == "done":
                    print("✅ 未连线输出槽场景烘焙成功(应给出可接受行为)")
                    return 0
            elif m["type"] == "graph.error":
                print("=== graph.error ===")
                print(m.get("message", "")[:1500])
                return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
