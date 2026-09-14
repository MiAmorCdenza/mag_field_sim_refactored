"""接线审计:哪些边是"真数据依赖",哪些只是仪式性连接。

背景(设计讨论结论):本系统里"节点存在 + 参数"才是真语义,边只应表示数据
依赖。但画布上大量 prev/next 链、species→types、injection→init 等边并不参与
计算,造成"画布 ≠ 运行时"(实测:未接线的物种节点照样参与生成、删掉注入的
数据线注入照样生效)。

本工具对同一张图做若干**删边/删节点**变体,打印编译出来的
  - 粒子域执行计划(ops 顺序、emitter/target 端口、step 的 slots)
  - 渲染域绑定表(每个渲染节点的 data 源)
据此判定每条边的性质(数据依赖 / 顺序锚点 / 纯装饰)。

运行: python tests/audit_wiring.py [图路径]
"""
from __future__ import annotations

import copy
import functools
import json
import os
import sys

print = functools.partial(print, flush=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import Graph, Lattice, Registry  # noqa: E402


def load(reg, doc):
    g = Graph(reg, Lattice.from_json(doc.get("lattice")))
    g.load_json(doc)
    return g


def strip_edges(doc, ports, node_ids=None):
    """删掉端口名属于 ports 的边(node_ids 限定只在这些节点之间删)。"""
    d = copy.deepcopy(doc)
    out = []
    for e in d["edges"]:
        if e["from"][1] in ports or e["to"][1] in ports:
            if node_ids is None or (e["from"][0] in node_ids and e["to"][0] in node_ids):
                continue
        out.append(e)
    d["edges"] = out
    return d


def drop_edge(doc, to_node, to_port):
    d = copy.deepcopy(doc)
    d["edges"] = [e for e in d["edges"]
                  if not (e["to"][0] == to_node and e["to"][1] == to_port)]
    return d


def drop_node(doc, nid):
    d = copy.deepcopy(doc)
    d["nodes"] = [n for n in d["nodes"] if n["id"] != nid]
    d["edges"] = [e for e in d["edges"]
                  if e["to"][0] != nid and e["from"][0] != nid]
    return d


def set_param(doc, nid, key, value):
    d = copy.deepcopy(doc)
    for n in d["nodes"]:
        if n["id"] == nid:
            n["params"] = {**(n.get("params") or {}), key: value}
    return d


def describe(reg, doc, label):
    g = load(reg, doc)
    plan = g.particle_plan()
    ops = []
    for o in plan["ops"]:
        txt = f"{o['kind']}({o['node']})"
        if o["kind"] == "step":
            txt += " slots=" + json.dumps(o["slots"])
        if o["kind"] in ("emitter", "injection"):
            txt += " in=" + json.dumps(o["inputs"])
        ops.append(txt)
    binds = [(b["node_id"], b["type"].replace("render_item_", ""),
              b["inputs"].get("data"))
             for b in g.render_bindings()]
    print(f"■ {label}")
    print(f"   计划: {' → '.join(ops)}   slow_path={plan['slow_path']}")
    print(f"   渲染: " + "  ".join(
        f"{nid}[{t}]{'←' + str(d) if d else ''}" for nid, t, d in binds))
    return g, plan


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "graphs", "preset_dipole_single.json")
    with open(path, encoding="utf-8") as f:
        base = json.load(f)
    reg = Registry([os.path.join(ROOT, "nodes")])
    reg.scan()

    pnodes = {n["id"] for n in base["nodes"]
              if n["type"] in ("particle_emitter", "particle_species",
                               "particle_injection", "boris_integrator",
                               "output_encoder", "leapfrog_integrator",
                               "rk4_integrator", "verlet_integrator")}
    rnodes = {n["id"] for n in base["nodes"]
              if n["type"].startswith("render_")}
    emitter = next((n["id"] for n in base["nodes"]
                    if n["type"] == "particle_emitter"), None)
    stepper = next((n["id"] for n in base["nodes"]
                    if n["type"].endswith("_integrator")), None)
    encoder = next((n["id"] for n in base["nodes"]
                    if n["type"] == "output_encoder"), None)
    holder = next((n["id"] for n in base["nodes"]
                   if n["type"] == "output_slot"), None)
    lines = next((n["id"] for n in base["nodes"]
                  if n["type"] == "render_item_field_lines"), None)

    variants = [("基线", base)]
    if pnodes:
        variants.append(("删粒子域链 prev/next(保留数据线)",
                         strip_edges(base, {"prev", "next"}, pnodes)))
    if rnodes:
        variants.append(("删渲染域链 prev/next(保留 data)",
                         strip_edges(base, {"prev", "next"}, rnodes)))
    if encoder:
        variants.append((f"删编码器节点 {encoder}", drop_node(base, encoder)))
    if stepper:
        variants.append((f"删 {holder}→{stepper}.b 数据线",
                         drop_edge(base, stepper, "b")))
    if emitter:
        variants.append((f"删注入→{emitter}.init 数据线",
                         drop_edge(base, emitter, "init")))
        variants.append((f"删物种→{emitter}.types 数据线",
                         drop_edge(base, emitter, "types")))
    if lines:
        variants.append((f"删 {lines}.data 数据线", drop_edge(base, lines, "data")))
    if holder:
        variants.append((f"{holder}.slot 参数与 outputs JSON 不一致(改成 Bx)",
                         set_param(base, holder, "slot", "Bx")))

    print(f"审计图: {os.path.relpath(path, ROOT)}({len(base['nodes'])} 节点)")
    print(f"outputs 槽位声明: {json.dumps(base.get('outputs'))}\n")
    for label, doc in variants:
        describe(reg, doc, label)
    print("\n判读:ops 顺序变化 = 该链是**顺序锚点**;slots/inputs 变化 = **数据依赖**;")
    print("      完全不变 = 纯装饰(画布在骗人,应删除或改成真语义)")


if __name__ == "__main__":
    main()
