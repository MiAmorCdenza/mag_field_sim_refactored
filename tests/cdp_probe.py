"""CDP 探针:连接无头 Edge 页面,在浏览器内执行诊断 JS。

用法: python tests/cdp_probe.py <表达式...>
  或 --stdin 从标准输入读表达式
前置: msedge --headless --remote-debugging-port=9222 http://127.0.0.1:8001/
"""
import asyncio
import json
import sys

import websockets


async def main():
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:9222/json") as r:
        targets = json.loads(r.read())
    pages = [t for t in targets if t.get("type") == "page"]
    # 优先匹配我们的服务器地址,否则取第一个真实页面
    page = next((t for t in pages if "127.0.0.1" in t.get("url", "")), None)
    if page is None:
        page = pages[0]
    print(f"[probe] 目标: {page['url']}")
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

        exprs = sys.argv[1:]
        if exprs == ["--stdin"]:
            exprs = [sys.stdin.read()]
        for expr in exprs:
            r = await call("Runtime.evaluate",
                           {"expression": expr, "returnByValue": True,
                            "awaitPromise": True})
            if "exceptionDetails" in r.get("result", {}):
                print(f"异常: {r['result']['exceptionDetails'].get('text')}")
            else:
                val = r["result"].get("result", {}).get("value")
                print(json.dumps(val, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
