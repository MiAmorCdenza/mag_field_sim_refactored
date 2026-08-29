"""CDP 截图:截取当前已加载页面(不重载,避免连接时序)。"""
import asyncio
import base64
import json
import sys

import websockets


async def main():
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:9222/json") as r:
        targets = json.loads(r.read())
    pages = [t for t in targets if t.get("type") == "page"]
    page = next((t for t in pages if "127.0.0.1" in t.get("url", "")), None) or pages[0]
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
        msg_id = 0

        async def call(method, params=None):
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": method,
                                      "params": params or {}}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == msg_id:
                    return m

        # 状态检查
        r = await call("Runtime.evaluate", {
            "expression": "({conn: document.getElementById('conn-status').textContent, "
                          "nodes: window.editor.graph._nodes.length})",
            "returnByValue": True})
        print("[state]", r["result"].get("result", {}).get("value"))
        shot = await call("Page.captureScreenshot", {"format": "png"})
        data = shot["result"]["data"]
        with open(sys.argv[1], "wb") as f:
            f.write(base64.b64decode(data))
        print("[shot]", sys.argv[1], len(data), "chars base64")


if __name__ == "__main__":
    asyncio.run(main())
