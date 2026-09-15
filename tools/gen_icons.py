"""生成节点像素图(SVG):16x16 像素画 → static/icons/*.svg + index.json。

为什么用 SVG 而不是 PNG:矢量 + shape-rendering=crispEdges,任意放大都是硬边
像素风;单文件几百字节,可直接进仓库、进便携包,也方便以后改格子。

色板(每个字形共用一张 16x16 字符网格):
    .  透明      #  主色      +  亮色      -  暗色      o  第二色(强调)
每张图有各自的调色板(见 GLYPHS 的 pal)。

用法:python tools/gen_icons.py
输出:static/icons/<name>.svg(16x16 viewBox)+ static/icons/index.json
      index.json 里给出 节点类型 → 图标名 的映射(前端按它取图,取不到回退 emoji)
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "icons")

# ---------------------------------------------------------------- 像素字形
# 全部 16x16。风格:深色描边 + 高饱和主体 + 一个亮色高光,在深色 UI 上清晰。
GLYPHS = {
    # 马蹄形磁铁(偶极/内部场)
    "magnet": (dict(H="#e5484d", L="#ff8a8a", D="#7a1f22", P="#8f9bb3"), [
        "................",
        "................",
        "....DDDDDDDD....",
        "...DHHHHHHHHD...",
        "..DHHLLLLLLHHD..",
        "..DHHLLLLLLHHD..",
        "..DHHHHHHHHHHD..",
        "..DHHD....DHHD..",
        "..DHHD....DHHD..",
        "..DHHD....DHHD..",
        "..DHHD....DHHD..",
        "..DPPD....DPPD..",
        "..DPPD....DPPD..",
        "..DDDD....DDDD..",
        "................",
        "................",
    ]),
    # 地球 + 磁力线弧(外部场模型 T89/T96/T01/T04/TS05/TA16)
    "globe": (dict(H="#3b7dd8", L="#7fc4ff", D="#1b3f70", P="#ffd36a"), [
        "................",
        ".....DDDDDD.....",
        "...DDHHHHHHDD...",
        "..DHHHLLLHHHHD..",
        ".DHHHLLLLLHHHHD.",
        ".DHHHDDHHDDHHHD.",
        ".DHHD.DHHD.DHHD.",
        "PDHD..DHHD..DHDP",
        "PDHD..DHHD..DHDP",
        ".DHHD.DHHD.DHHD.",
        ".DHHHDDHHDDHHHD.",
        ".DHHHLLLLLHHHHD.",
        "..DHHHLLLHHHHD..",
        "...DDHHHHHHDD...",
        ".....DDDDDD.....",
        "................",
    ]),
    # 插座/端口(输出槽)
    "plug": (dict(H="#9aa7b8", L="#d7e2f0", D="#4a5568", P="#ffb454"), [
        "................",
        "................",
        "..DDDDDDDDDDDD..",
        "..DHHHHHHHHHHD..",
        "..DHLLHHHHLLHD..",
        "..DHLLHHHHLLHD..",
        "..DHHHHHHHHHHD..",
        "..DHHHHHHHHHHD..",
        "..DDDDDDDDDDDD..",
        "....DPPPPD......",
        "....DPPPPD......",
        "....DPPPPD......",
        "....DPPPPD......",
        "....DDDDDD......",
        "................",
        "................",
    ]),
    # 循环箭头(积分器:boris/leapfrog/rk4/verlet)
    "loop": (dict(H="#4cc38a", L="#8ff0bb", D="#1c5c40", P="#ffd36a"), [
        "................",
        "......DDDD......",
        "....DDHHHHDD....",
        "...DHHHLLHHHD...",
        "..DHHHD..DHHHD..",
        "..DHHD....DHHD..",
        ".DHHD......DHHD.",
        ".DHHD......DHHD.",
        ".DHHD......DHHD.",
        "..DHHD....DHHD..",
        "..DHHHD..DHHHDPP",
        "...DHHHLLHHHDPP.",
        "....DDHHHHDDPP..",
        "......DDDD......",
        "................",
        "................",
    ]),
    # 喷嘴 + 粒子(发射器)
    "nozzle": (dict(H="#c9a227", L="#ffe28a", D="#6b5410", P="#7fd1ff"), [
        "................",
        "....DDDDDDDD....",
        "...DHHHHHHHHD...",
        "...DHLLLLLLHD...",
        "...DHHHHHHHHD...",
        "....DDHHHHDD....",
        ".....DHHHD......",
        ".....DHHHD......",
        "......DHD.......",
        "................",
        "...P...P...P....",
        "..P.P.P.P.P.P...",
        "...P...P...P....",
        "................",
        "................",
        "................",
    ]),
    # 表格(物种/种群行表)
    "table": (dict(H="#5b8def", L="#a9c8ff", D="#26407a", P="#ffd36a"), [
        "................",
        "..DDDDDDDDDDDD..",
        "..DHHHHHHHHHHD..",
        "..DLLLLLLLLLLD..",
        "..DHHHHDHHHHHD..",
        "..DHHHHDHHHHHD..",
        "..DLLLLLLLLLLD..",
        "..DHHHHDHHHHHD..",
        "..DHHHHDHHHHHD..",
        "..DLLLLLLLLLLD..",
        "..DHHHHDHHHHHD..",
        "..DHHHHDHHHHHD..",
        "..DDDDDDDDDDDD..",
        "................",
        "................",
        "................",
    ]),
    # 准星(单粒子注入)
    "target": (dict(H="#ff6b6b", L="#ffc9c9", D="#7a1f22", P="#e6edf3"), [
        "................",
        ".......PP.......",
        ".......PP.......",
        "....DDDPPDDD....",
        "...DHHHPPHHHD...",
        "..DHHHHPPHHHHD..",
        "..DHHHDDDDHHHD..",
        "PPDHHD.HH.DHHDPP",
        "PPDHHD.HH.DHHDPP",
        "..DHHHDDDDHHHD..",
        "..DHHHHPPHHHHD..",
        "...DHHHPPHHHD...",
        "....DDDPPDDD....",
        ".......PP.......",
        ".......PP.......",
        "................",
    ]),
    # 括号 + 比特流(编码器)
    "packet": (dict(H="#b58cff", L="#dcc9ff", D="#4a2f80", P="#7fd1ff"), [
        "................",
        "..DDD......DDD..",
        "..DHD......DHD..",
        "..DHD.PPPP.DHD..",
        "..DHD.P..P.DHD..",
        "..DHD......DHD..",
        "..DHD.PPPP.DHD..",
        "..DHD.P....DHD..",
        "..DHD......DHD..",
        "..DHD.PPPP.DHD..",
        "..DHD.P..P.DHD..",
        "..DHD......DHD..",
        "..DDD......DDD..",
        "................",
        "................",
        "................",
    ]),
    # 弯曲磁力线(场线渲染项)
    "lines": (dict(H="#4da6ff", L="#a8d5ff", D="#1d4a80", P="#ff6b6b"), [
        "................",
        "....DDD.........",
        "..DDHHHDD.......",
        ".DHHHHHHHD......",
        ".DHHD..DHHD.....",
        "DHHD....DHHD....",
        "DHHD.....DHHD...",
        "DHHD......DHHD..",
        ".DHHD......DHHD.",
        "..DHHD......DHD.",
        "...DHHD.....DHD.",
        "....DHHD....DHD.",
        ".....DHHD..DHHD.",
        "......DHHDDHHD..",
        ".......DHHHHD...",
        "........DDDD....",
    ]),
    # 散点(粒子渲染项 / 粒子域)
    "dots": (dict(H="#7fd1ff", L="#d6f2ff", D="#255a80", P="#ff9b6a"), [
        "................",
        "....DD..........",
        "...DHHD.....DD..",
        "...DHHD....DHHD.",
        "....DD.....DHHD.",
        "................",
        "........DD......",
        ".......DHHD.....",
        ".......DHHD.....",
        "........DD......",
        "..DD............",
        ".DHHD.......DD..",
        ".DHHD......DHHD.",
        "..DD.......DHHD.",
        "................",
        "................",
    ]),
    # 渐隐拖尾
    "trail": (dict(H="#8ff0bb", L="#d8ffe9", D="#1c5c40", P="#4cc38a"), [
        "................",
        ".............DD.",
        "............DHHD",
        "...........DHHD.",
        "..........DHHD..",
        ".........DHHD...",
        "........DHHD....",
        ".......DHHD.....",
        "......DHHD......",
        ".....DHHD.......",
        "....DHHD........",
        "...DHHD.........",
        "..DHD...........",
        "..DD............",
        "................",
        "................",
    ]),
    # 圆锥(俯仰角锥)
    "cone": (dict(H="#ffcc66", L="#ffe9b0", D="#7a5a10", P="#66ffcc"), [
        "................",
        ".......DD.......",
        "......DHHD......",
        "......DHHD......",
        ".....DHHHD......",
        "....DHHHHDD.....",
        "....DHHHHHD.....",
        "...DHHHHHHHD....",
        "...DHHHHHHHD....",
        "..DHHHHHHHHHD...",
        "..DHHHHHHHHHD...",
        ".DHHHHHHHHHHHD..",
        ".DHHHHHHHHHHHD..",
        "DDDDDDDDDDDDDD..",
        "................",
        "................",
    ]),
    # 播放(渲染管线起始)
    "play": (dict(H="#4cc38a", L="#8ff0bb", D="#1c5c40", P="#e6edf3"), [
        "................",
        "..DDDD..........",
        "..DHHDD.........",
        "..DHHHDD........",
        "..DHHHHHDD......",
        "..DHHHHHHHDD....",
        "..DHHHHHHHHHD...",
        "..DHHHHHHHHHHD..",
        "..DHHHHHHHHHHD..",
        "..DHHHHHHHHHD...",
        "..DHHHHHHHDD....",
        "..DHHHHHDD......",
        "..DHHHDD........",
        "..DHHDD.........",
        "..DDDD..........",
        "................",
    ]),
    # 折线(电场线)
    "wave": (dict(H="#ff9b6a", L="#ffd0b0", D="#7a3a1d", P="#7fd1ff"), [
        "................",
        "................",
        "..........DD....",
        ".........DHHD...",
        "........DHHD....",
        ".......DHHD.....",
        "......DHHD......",
        ".....DHHD.......",
        "....DHHD........",
        "...DHHD.........",
        "..DHHD..........",
        ".DHHD...........",
        ".DHD............",
        ".DD.............",
        "................",
        "................",
    ]),
    # 求和/运算(组合节点 add/mul/blend…)
    "math": (dict(H="#9aa7b8", L="#d7e2f0", D="#4a5568", P="#ffd36a"), [
        "................",
        "..DDDDDDDDDD....",
        "..DHHHHHHHHD....",
        "..DHHD......D...",
        "...DHHD.........",
        "....DHHD........",
        ".....DHHD.......",
        "......DHHD......",
        ".....DHHD.......",
        "....DHHD........",
        "...DHHD.........",
        "..DHHD......D...",
        "..DHHHHHHHHD....",
        "..DDDDDDDDDD....",
        "................",
        "................",
    ]),
    # 齿轮(通用/其它)
    "gear": (dict(H="#8b98a8", L="#cfd8e3", D="#3d4655", P="#ffd36a"), [
        "................",
        "...D.D....D.D...",
        "...DHHD..DHHD...",
        "....DHHDDHHD....",
        "..DDDHHHHHHDDD..",
        "..DHHHHHHHHHHD..",
        ".DDHHH.DD.HHHDD.",
        ".DHHH..DD..HHHD.",
        ".DHHH..DD..HHHD.",
        ".DDHHH.DD.HHHDD.",
        "..DHHHHHHHHHHD..",
        "..DDDHHHHHHDDD..",
        "....DHHDDHHD....",
        "...DHHD..DHHD...",
        "...D.D....D.D...",
        "................",
    ]),
}

# 节点类型 → 图标(按关键词匹配,顺序即优先级)。没命中的按 category 兜底。
KEYWORD_GLYPHS = [
    ("dipole", "magnet"),
    ("t89", "globe"), ("t96", "globe"), ("t01", "globe"), ("t04", "globe"),
    ("ts05", "globe"), ("ta16", "globe"),
    ("output_slot", "plug"),
    ("integrator", "loop"), ("boris", "loop"), ("leapfrog", "loop"),
    ("rk4", "loop"), ("verlet", "loop"),
    ("emitter", "nozzle"),
    ("population", "table"), ("species", "table"),
    ("injection", "target"),
    ("encoder", "packet"),
    ("efield", "wave"),
    ("field_lines", "lines"),
    ("trail", "trail"),
    ("pitch_cone", "cone"),
    ("particles", "dots"),
    ("pipeline_start", "play"),
    ("source_preview", "target"),
    ("diagnostics", "table"),
    ("camera", "play"),
    ("add", "math"), ("mul", "math"), ("blend", "math"), ("mask", "math"),
    ("imf_source", "wave"), ("tail", "lines"), ("magnetopause", "globe"),
    ("corotation", "loop"), ("convection", "loop"), ("shield", "globe"),
    ("gravity", "target"), ("atmosphere", "wave"), ("drag", "wave"),
    ("kp_source", "math"), ("day_source", "math"),
]
CATEGORY_GLYPHS = {
    "磁场": "globe",
    "粒子": "dots",
    "渲染": "lines",
    "输出": "plug",
    "组合": "math",
}


def svg_for(name: str, pal: dict, rows: list) -> str:
    """16x16 字符网格 → SVG(每像素一个 1x1 rect,crispEdges 硬边)。"""
    assert len(rows) == 16 and all(len(r) == 16 for r in rows), name
    color_of = {".": None, "H": pal["H"], "L": pal.get("L", pal["H"]),
                "D": pal.get("D", pal["H"]), "P": pal.get("P", pal["H"])}
    body = []
    for y, row in enumerate(rows):
        x = 0
        while x < 16:
            c = row[x]
            if c == ".":
                x += 1
                continue
            run = 1
            while x + run < 16 and row[x + run] == c:
                run += 1
            col = color_of[c]
            body.append('<rect x="%d" y="%d" width="%d" height="1" fill="%s"/>'
                        % (x, y, run, col))
            x += run
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
            'width="16" height="16" shape-rendering="crispEdges" '
            'role="img" aria-label="%s">\n  %s\n</svg>\n'
            % (name, "\n  ".join(body)))


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    for name, (pal, rows) in GLYPHS.items():
        with open(os.path.join(OUT, name + ".svg"), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write(svg_for(name, pal, rows))
    print("✓ 生成 %d 个像素图 → static/icons/" % len(GLYPHS))

    # 节点类型 → 图标:直接从引擎注册表读(加插件自动带上,不用改本文件)
    sys.path.insert(0, ROOT)
    from engine.registry import default_registry
    reg = default_registry()
    mapping, missing = {}, []
    for spec in reg.describe():
        t, cat = spec["type"], spec.get("category") or ""
        glyph = None
        for kw, g in KEYWORD_GLYPHS:
            if kw in t:
                glyph = g
                break
        if glyph is None:
            glyph = CATEGORY_GLYPHS.get(cat.split("/")[0], "gear")
            missing.append(t)
        mapping[t] = glyph
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8",
              newline="\n") as f:
        json.dump({"glyphs": sorted(GLYPHS), "types": mapping}, f,
                  ensure_ascii=False, indent=1)
        f.write("\n")
    print("✓ 映射 %d 个节点类型 → index.json" % len(mapping))
    if missing:
        print("  (按类别兜底:%s)" % ", ".join(sorted(missing)[:8]) +
              (" …" if len(missing) > 8 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
