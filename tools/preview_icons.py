"""把生成的像素图拼成一张预览图(便于肉眼检查),不进产品代码。

用法:python tools/preview_icons.py → %TEMP%\\icons_preview.html + 提示截图命令
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS = os.path.join(ROOT, "static", "icons")

names = json.load(open(os.path.join(ICONS, "index.json"), encoding="utf-8"))["glyphs"]
cells = []
for n in names:
    svg = open(os.path.join(ICONS, n + ".svg"), encoding="utf-8").read()
    svg = svg.replace('width="16" height="16"', 'width="96" height="96"')
    cells.append('<div class=c><div class=img>' + svg +
                 '</div><div class=n>' + n + '</div></div>')
html = ('<!doctype html><meta charset=utf-8><style>'
        'body{background:#0d1117;color:#e6edf3;font:12px system-ui;'
        'display:flex;flex-wrap:wrap;gap:14px;padding:16px;margin:0}'
        '.c{text-align:center}'
        '.img{padding:8px;background:#161b22;border:1px solid #30363d;border-radius:6px}'
        '.n{color:#7d8b9a;margin-top:4px}</style>' + ''.join(cells))
out = os.path.join(os.environ.get("TEMP", "."), "icons_preview.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(out)
