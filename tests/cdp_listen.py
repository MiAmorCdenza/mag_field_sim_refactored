"""CDP 监听:不重载,只监听当前页面新产生的 console 错误。"""
import asyncio
import json

import websockets


async def main():
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:9222/json") as r:
        targets = json.loads(r.read())
    pages = [t for t in targets if t.get("type") == "page"]
    page = next((t for t in pages if "127.0.0.1" in t.get("url", "")), None) or pages[0]
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
        msg_id = 0
        errors = []

        async def call(method, params=None):
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": method,
                                      "params": params or {}}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == msg_id:
                    return m
                if m.get("method") == "Runtime.consoleAPICalled":
                    p = m["params"]
                    if p.get("type") in ("error", "warning"):
                        args = [a.get("value") or a.get("description") or ""
                                for a in p.get("args", [])]
                        errors.append(f"[{p['type']}] {' '.join(map(str, args))}")
                elif m.get("method") == "Runtime.exceptionThrown":
                    d = m["params"].get("exceptionDetails", {})
                    errors.append(f"[exception] {d.get('text')}")

        await call("Runtime.enable")
        # 探针:当前渲染项状态(粒子网格计数 + 场线数)
        r = await call("Runtime.evaluate", {
            "expression": "(() => { const out = {}; "
                          "for (const [k, inst] of window.renderHost.items) { "
                          "const pc = Object.values(inst.meshes || {})"
                          ".reduce((a, m) => a + m.count, 0); "
                          "out[k] = { particles: pc, lines: (inst.lines || []).length }; } "
                          "return out; })()",
            "returnByValue": True})
        print("[state]", json.dumps(r["result"].get("result", {}).get("value"),
                                    ensure_ascii=False))
        await asyncio.sleep(5)
        print("[new-errors]", len(errors))
        for e in errors[:8]:
            print(" ", e)


if __name__ == "__main__":
    asyncio.run(main())
