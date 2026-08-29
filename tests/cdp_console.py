"""CDP 控制台采集:重载页面,收集 console/异常输出。"""
import asyncio
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
                if m.get("method") in ("Runtime.consoleAPICalled",
                                       "Runtime.exceptionThrown"):
                    dump(m)

        def dump(m):
            if m.get("method") == "Runtime.consoleAPICalled":
                p = m["params"]
                args = [a.get("value") or a.get("description") or a.get("type")
                        for a in p.get("args", [])]
                print(f"[console.{p.get('type')}] {' '.join(map(str, args))}")
            else:
                d = m["params"].get("exceptionDetails", {})
                print(f"[exception] {d.get('text')} {d.get('url', '')}"
                      f"@{d.get('lineNumber')}")

        await call("Runtime.enable")
        await call("Page.enable")
        await call("Page.reload", {"ignoreCache": True})
        await asyncio.sleep(8)
        r = await call("Runtime.evaluate", {
            "expression": "({nodes: window.editor.graph._nodes.length, "
                          "items: window.renderHost.items.size})",
            "returnByValue": True})
        print("[final]", r["result"].get("result", {}).get("value"))


if __name__ == "__main__":
    asyncio.run(main())
