"""WebSocket 客户端端到端测试。

前置:服务端已启动
  mf_server --root . --port 8001 --particles 5000
运行: python tests/test_ws_client.py
"""
import asyncio
import functools
import json
import struct

import websockets

print = functools.partial(print, flush=True)  # 管道输出即时可见

HOST = "ws://127.0.0.1:8001/ws"


async def recv_text(ws, timeout=30):
    """接收文本 JSON(跳过二进制粒子帧)。"""
    while True:
        frame = await asyncio.wait_for(ws.recv(), timeout)
        if isinstance(frame, (bytes, bytearray)):
            continue
        return json.loads(frame)


async def main():
    async with websockets.connect(HOST, max_size=None) as ws:
        # 1) init_config
        msg = await recv_text(ws, 10)
        assert msg["type"] == "init_config", msg
        slots = list(msg["graph"]["outputs"].keys())
        print(f"✓ init_config,槽位: {slots}", flush=True)

        # 2) node.param → bake_progress queued/computing/done
        await ws.send(json.dumps({"type": "node.param", "node": "kp",
                                  "name": "kp", "value": 3.5}))
        states = []
        while True:
            m = await recv_text(ws, 60)
            if m["type"] == "bake_progress":
                states.append(m["state"])
                print("  bake_progress:", m["state"])
                if m["state"] in ("done", "error"):
                    break
        assert "computing" in states and states[-1] == "done", states
        print("✓ 参数更新 → 重烘焙完成")

        # 3) set_particle_count → 等二进制帧
        await ws.send(json.dumps({"type": "set_particle_count", "value": 5000}))
        got_bin = False
        while not got_bin:
            frame = await asyncio.wait_for(ws.recv(), 15)
            if isinstance(frame, (bytes, bytearray)):
                got_bin = True
        hlen = struct.unpack("<I", frame[:4])[0]
        header = json.loads(frame[4:4 + hlen])
        body = frame[4 + hlen:]
        assert header["type"] == "s", header
        assert header["n"] == 5000, f"header: {header}"
        assert len(body) == 5000 * 21, f"body: {len(body)}"
        print("✓ 二进制帧: n=5000,21B/粒子,头 JSON:", header)

        # 4) graph.upload(重传同一图 → 全量重烘焙)
        await ws.send(json.dumps({"type": "graph.upload", "graph": msg["graph"]}))
        while True:
            m = await recv_text(ws, 60)
            if m["type"] == "bake_progress":
                print("  bake_progress:", m["state"])
                if m["state"] == "done":
                    break
        print("✓ graph.upload → 重烘焙完成")

        # 4.5) 枚举参数(通用值通道)
        await ws.send(json.dumps({"type": "node.param", "node": "tail",
                                  "name": "model", "value": "harris"}))
        while True:
            m = await recv_text(ws, 60)
            if m["type"] == "bake_progress":
                print("  bake_progress:", m["state"])
                if m["state"] == "done":
                    break
        print("✓ 枚举参数(尾模型 → harris)→ 重烘焙完成")

        # 5) respawn + 粒子数回退
        await ws.send(json.dumps({"type": "respawn"}))
        await ws.send(json.dumps({"type": "set_particle_count", "value": 100}))
        await asyncio.sleep(0.5)
        print("✓ respawn / 粒子数变更已受理")

        # 6) 插件热加载:丢文件 → 服务器自动重扫并广播新节点面板
        import os
        plugin_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "user_nodes", "hot_test.py")
        with open(plugin_path, "w", encoding="utf-8") as f:
            f.write('''from engine import register_node, Node, Param, Field\n'''
                    '''import numpy as np\n\n'''
                    '''@register_node(type="hot_test_node", name="热加载测试", '''
                    '''category="用户/测试", inputs={}, '''
                    '''outputs={"field": "vector_field"}, '''
                    '''params={"v": Param("scalar", default=1.0)}, version=1)\n'''
                    '''class HotTestNode(Node):\n'''
                    '''    def compute(self):\n'''
                    '''        lat = self.lattice\n'''
                    '''        d = np.full((lat.nx, lat.ny, lat.nz, 3), self.params["v"])\n'''
                    '''        return {"field": Field("vector", d, lat)}\n''')
        try:
            got_registry = False
            loop = asyncio.get_event_loop()
            deadline = loop.time() + 20
            while loop.time() < deadline:
                m = await recv_text(ws, 15)
                if m["type"] == "registry":
                    types = {t["type"] for t in m["types"]}
                    if "hot_test_node" in types:
                        got_registry = True
                        break
            assert got_registry, "未收到含 hot_test_node 的 registry 广播"
            print("✓ 插件热加载:丢文件 → 自动注册 hot_test_node")
        finally:
            os.remove(plugin_path)


asyncio.run(main())
print("WS 客户端端到端测试全部通过 ✅")
