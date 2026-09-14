"""预设完整性测试(引导页 #33):发现 + 载入 + 计划/绑定无告警。

跟着引导页的自动发现走 —— **加一个 preset_*.json 就自动被本测试覆盖**:

  1. GET /api/presets        列表非空,每张卡片字段齐全(id/name/desc/nodes)
  2. GET /api/preset?id=...  取回图 JSON,能被引擎加载
  3. 编译粒子计划 + 渲染绑定:非 custom 预设必须**零告警**
     (保证出厂预设不会带"无 B 表/无编码器/渲染项未接线"这类问题)
  4. custom 预设(空画布)允许有告警(它本来就没有任何节点)

前置:服务端已启动(默认端口 8001)
运行: python tests/test_presets.py
"""
import functools
import json
import os
import sys
import urllib.request

print = functools.partial(print, flush=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import Graph, Lattice, Registry  # noqa: E402

API = "http://127.0.0.1:8001/api"


def get(path):
    with urllib.request.urlopen(API + path, timeout=20) as r:
        return json.load(r)


def main():
    cards = get("/presets")
    assert cards, "引导页没有任何预设卡片(graphs/preset_*.json 为空?)"
    print(f"✓ 发现 {len(cards)} 个预设")
    for c in cards:
        for k in ("id", "name", "desc", "nodes", "edges", "lattice", "custom"):
            assert k in c, f"卡片缺字段 {k}: {c}"
    assert any(c["custom"] for c in cards), "应有一个「自定义/空预设」入口"
    print("✓ 卡片字段齐全,且存在自定义入口: " +
          ", ".join(c["id"] for c in cards if c["custom"]))

    reg = Registry([os.path.join(ROOT, "nodes")])
    reg.scan()
    for c in cards:
        doc = get(f"/preset?id={c['id']}")
        assert isinstance(doc, dict) and "nodes" in doc, c["id"]
        assert len(doc["nodes"]) == c["nodes"], (c["id"], len(doc["nodes"]), c["nodes"])
        lat = Lattice.from_json(doc.get("lattice")) if doc.get("lattice") else None
        g = Graph(reg, lat)
        g.load_json(doc)
        assert not g.skipped_edges, (c["id"], g.skipped_edges)
        plan = g.particle_plan()
        binds = g.render_bindings()
        unwired = [b["node_id"] for b in binds
                   if b.get("needs_data") and not b.get("has_data")]
        selftest = c["id"] == "custom_empty" or c.get("custom")
        if selftest:
            print(f"✓ {c['id']:16s} 空预设:节点 {len(doc['nodes'])}(允许无算子)")
            continue
        codes = [w["code"] for w in plan["warnings"]]
        assert not codes, f"{c['id']} 预设带粒子计划告警: {codes}"
        assert not plan["slow_path"], f"{c['id']} 预设触发 slow_path"
        assert not unwired, f"{c['id']} 预设的渲染项未接数据源: {unwired}"
        kinds = [o["kind"] for o in plan["ops"]]
        assert "emitter" in kinds and "step" in kinds and "encode" in kinds, kinds
        slots = [o["slots"]["b"] for o in plan["ops"] if o["kind"] == "step"]
        assert slots and all(slots), f"{c['id']} 预设的步进算子缺 B 槽位: {slots}"

        # 真的烘焙一遍:参数默认值/节点实现的问题只有算一遍才会暴露
        # (实测踩过:imf 节点直接索引 self.params["parker_custom"] → KeyError →
        #  服务器 bake_progress 报 error,而只编译计划是看不出来的)
        import numpy as np
        import time
        t0 = time.perf_counter()
        baked = g.evaluate(sorted(doc.get("outputs") or {}) or ["B"])
        dt = time.perf_counter() - t0
        for slot, fld in baked.items():
            arr = np.asarray(fld.data, dtype=float)
            assert np.all(np.isfinite(arr)), f"{c['id']} 槽位 {slot} 含非有限值"
            assert float(np.max(np.abs(arr))) > 0.0, f"{c['id']} 槽位 {slot} 全零"
        print(f"✓ {c['id']:16s} 节点 {len(doc['nodes']):2d} 边 {len(doc['edges']):2d} "
              f"算子 {'→'.join(kinds)} 渲染项 {len(binds)} 零告警 "
              f"烘焙 {dt:.1f}s({','.join(baked)})")

    print("预设完整性测试全部通过 ✅")


if __name__ == "__main__":
    main()
