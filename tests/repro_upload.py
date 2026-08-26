"""模拟前端 exportGraph 的上传行为:权威图 + 编辑器变换 → 上传 → 观察烘焙。

编辑器 exportGraph 与服务器权威快照的差异:
1) lattice 硬编码为 {"preset": "coarse"}
2) 节点参数/输入默认值来自 properties(含 None 默认端口)
运行: python tests/repro_upload.py
"""
import asyncio
import json
import urllib.request

import websockets

HOST = "ws://127.0.0.1:8001/ws"


def fetch_graph():
    with urllib.request.urlopen("http://127.0.0.1:8001/api/graph", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def editor_transform(doc):
    """复刻 editor.js exportGraph 对图 JSON 的变换。"""
    nodes = []
    for nd in doc["nodes"]:
        props = dict(nd.get("params") or {})
        for k, v in (nd.get("input_defaults") or {}).items():
            props["in:" + k] = v
        props["spec_type"] = nd["type"]
        props["json_id"] = nd["id"]
        params = {k: v for k, v in props.items()
                  if k != "spec_type" and k != "json_id" and not k.startswith("in:")}
        input_defaults = {k[3:]: v for k, v in props.items() if k.startswith("in:")}
        nodes.append({"id": props["json_id"], "type": props["spec_type"],
                      "params": params, "input_defaults": input_defaults,
                      "pos": [round(nd["pos"][0]), round(nd["pos"][1])]})
    edges = list(doc["edges"])
    return {"version": 1, "lattice": {"preset": "coarse"},  # exportGraph 硬编码
            "nodes": nodes, "edges": edges, "outputs": dict(doc["outputs"])}


async def recv_text(ws, timeout=30):
    while True:
        frame = await asyncio.wait_for(ws.recv(), timeout)
        if isinstance(frame, (bytes, bytearray)):
            continue
        return json.loads(frame)


async def main():
    doc = fetch_graph()
    upload = editor_transform(doc)
    print(f"转换后: {len(upload['nodes'])} 节点, lattice={upload['lattice']}")

    async with websockets.connect(HOST, max_size=None) as ws:
        init = await recv_text(ws, 10)
        assert init["type"] == "init_config"
        await ws.send(json.dumps({"type": "graph.upload", "graph": upload}))
        while True:
            m = await recv_text(ws, 300)
            if m["type"] == "bake_progress":
                print("bake_progress:", m["state"])
                if m["state"] == "error":
                    print("=== 服务器错误详情 ===")
                    print(m.get("note", ""))
                    return 1
                if m["state"] == "done":
                    print("✅ 上传烘焙成功")
                    return 0
            elif m["type"] == "graph.error":
                print("=== graph.error ===")
                print(m.get("message", ""))
                return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
