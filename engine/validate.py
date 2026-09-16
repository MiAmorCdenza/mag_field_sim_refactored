"""统一图校验入口(#45)—— 预设**写盘之前**必须过这一关。

为什么要有它:C++ 侧读图是不校验的(直接 load_graph),而 Python 侧早有一套最严的
口径(tests/test_presets.py:能加载 + **计划零告警** + **能烘焙**)。把口径收拢到这里,
服务端保存预设前调一次即可,避免出现"两套图校验逻辑各说各话"。

口径(与回归测试一致):
  1. 结构:version / nodes / edges 基本形状,节点类型必须在注册表里
  2. 能加载:Graph.load_json 不抛(GraphError → errors)
  3. 零告警:particle_plan()["warnings"] 必须为空(否则现场会出现红框/退化计划)
  4. 能烘焙:声明槽位(或引擎推导的槽位)必须求出**全有限**的值
返回 JSON 字符串(C++ 直接透传给前端):
  {"ok":bool, "errors":[...], "warnings":[...], "slots":[...],
   "nodes":n, "edges":m, "bake_ms":int, "ops":[...]}
errors 非空 = 拒绝保存;warnings 非空 = 默认也拒绝(调用方可 force 覆盖)。
"""
from __future__ import annotations

import json
import time

_REG = None          # 节点注册表(扫描一次,进程内复用)
_ROOT = "."


def _registry(root):
    global _REG, _ROOT
    if _REG is None or _ROOT != root:
        from engine.registry import Registry
        reg = Registry([f"{root}/nodes", f"{root}/user_nodes"])
        reg.scan()
        _REG, _ROOT = reg, root
    return _REG


def validate_graph(payload_json: str) -> str:
    """payload: {"root": ".", "graph": {...}} → 校验结果 JSON 字符串。"""
    t0 = time.monotonic()
    out = {"ok": False, "errors": [], "warnings": [], "slots": [],
           "nodes": 0, "edges": 0, "bake_ms": 0, "ops": []}
    try:
        payload = json.loads(payload_json)
    except Exception as e:
        out["errors"].append(f"payload 不是合法 JSON:{e}")
        return json.dumps(out, ensure_ascii=False)

    root = payload.get("root") or "."
    doc = payload.get("graph")
    if not isinstance(doc, dict):
        out["errors"].append("缺少 graph 字段")
        return json.dumps(out, ensure_ascii=False)

    out["nodes"] = len(doc.get("nodes") or [])
    out["edges"] = len(doc.get("edges") or [])

    # ---- 1/2) 结构 + 引擎加载 ----
    try:
        from engine import Graph, Lattice
    except Exception as e:                       # 引擎不可用:直接判失败,别放行坏图
        out["errors"].append(f"引擎导入失败:{e}")
        return json.dumps(out, ensure_ascii=False)

    # GraphError 的落点不固定(历史上在 graph/registry 里都出现过)→ 容错查找,
    # 找不到就退化成 Exception(只影响错误分类文案,不影响判定)
    GraphError = Exception
    for _mod in ("engine.errors", "engine.graph", "engine.registry", "engine"):
        try:
            _m = __import__(_mod, fromlist=["GraphError"])
            GraphError = getattr(_m, "GraphError")
            break
        except Exception:
            continue

    try:
        lat = Lattice.from_json(doc.get("lattice") or {"preset": "tiny"})
        g = Graph(_registry(root), lat)
        g.load_json(doc)
    except GraphError as e:
        out["errors"].append(f"图加载失败:{e}")
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:
        out["errors"].append(f"图加载异常:{type(e).__name__}: {e}")
        return json.dumps(out, ensure_ascii=False)

    # ---- 3) 计划零告警(与回归同口径)----
    try:
        plan = g.particle_plan()
        out["ops"] = [o.get("kind") for o in plan.get("ops", [])]
        for w in (plan.get("warnings") or []):
            code = w.get("code") if isinstance(w, dict) else str(w)
            node = w.get("node") if isinstance(w, dict) else ""
            out["warnings"].append(f"{code}" + (f" @{node}" if node else ""))
    except Exception as e:
        out["errors"].append(f"计划编译失败:{type(e).__name__}: {e}")
        return json.dumps(out, ensure_ascii=False)

    # 空图(自定义/空预设)允许:没有算子也不该拦
    if not doc.get("nodes"):
        out["ok"] = True
        out["bake_ms"] = int((time.monotonic() - t0) * 1000)
        return json.dumps(out, ensure_ascii=False)

    # ---- 4) 能烘焙且全有限 ----
    try:
        import numpy as np
        slots = sorted(g.outputs) or ["B"]
        out["slots"] = slots
        baked = g.evaluate(slots)
        for name in slots:
            fld = baked.get(name)
            if fld is None:
                out["errors"].append(f"槽位 {name} 未烘焙出结果")
                continue
            arr = getattr(fld, "data", None)
            if arr is None:
                out["errors"].append(f"槽位 {name} 无数据")
                continue
            if not np.isfinite(np.asarray(arr)).all():
                out["errors"].append(f"槽位 {name} 含非有限值(NaN/Inf)")
        if not slots and not out["errors"]:
            out["warnings"].append("no_baked_slot")
    except Exception as e:
        out["errors"].append(f"烘焙失败:{type(e).__name__}: {e}")

    out["bake_ms"] = int((time.monotonic() - t0) * 1000)
    out["ok"] = not out["errors"] and not out["warnings"]
    return json.dumps(out, ensure_ascii=False)
