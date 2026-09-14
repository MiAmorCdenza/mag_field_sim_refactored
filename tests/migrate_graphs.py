"""把现有图迁移到"显式顺序"模型(#28):

- 删除 prev/next 链边(粒子域与渲染域)
- 粒子域节点补 order 参数(值 = 历史链序语义:发射器10/物种20/注入25/步进30/编码40)
- 渲染项补 layer 参数(值 = 渲染项 JS 里原有的硬编码层:线1/粒子2/标记3)
- 删除 render_pipeline_start 的 next 链边(节点保留,承载全局参数)

用法: python tests/migrate_graphs.py [图路径 ...]
      默认处理 graphs/default_graph.json 与 graphs/preset_dipole_single.json
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 粒子域 order 默认(与 engine/graph.py::_PARTICLE_OP_ORDER 一致)
PARTICLE_ORDER = {
    "particle_emitter": 10,
    "particle_species": 20,
    "particle_injection": 25,
    "boris_integrator": 30,
    "leapfrog_integrator": 30,
    "rk4_integrator": 30,
    "verlet_integrator": 30,
    "output_encoder": 40,
}
# 渲染项 layer 默认(与渲染项 JS 里原有 layer 一致)
RENDER_LAYER = {
    "render_item_field_lines": 1,
    "render_item_efield_lines": 1,
    "render_item_diagnostics": 1,
    "render_item_particles": 2,
    "render_item_particle_trails": 2,
    "render_item_source_preview": 3,
}
ORDER_KEYS = ("order", "layer")


def migrate(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    before_edges = len(doc.get("edges", []))
    doc["edges"] = [e for e in doc.get("edges", [])
                    if e["from"][1] not in ("next",)
                    and e["to"][1] not in ("prev",)]
    added = []
    for n in doc.get("nodes", []):
        t = n["type"]
        params = dict(n.get("params") or {})
        if t in PARTICLE_ORDER and "order" not in params:
            params["order"] = PARTICLE_ORDER[t]
            added.append(f"{n['id']}.order={params['order']}")
        elif t in RENDER_LAYER and "layer" not in params:
            params["layer"] = RENDER_LAYER[t]
            added.append(f"{n['id']}.layer={params['layer']}")
        if params:
            n["params"] = params
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"✓ {os.path.relpath(path, ROOT)}: 删链边 {before_edges - len(doc['edges'])} 条,"
          f"补显式顺序 {len(added)} 处")
    for a in added:
        print("    " + a)


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        os.path.join(ROOT, "graphs", "default_graph.json"),
        os.path.join(ROOT, "graphs", "preset_dipole_single.json"),
    ]
    for t in targets:
        migrate(t)
