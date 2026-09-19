"""给外部场/内场模型节点补一句"来源 + 特性"(#54 续)。

用户要求:T89/IGRF 这类复杂模型不会细讲,**简单写写来源与特性就好**。
做法:写进节点类的 docstring —— 界面上「说明」区直接显示它,零重复维护。
规则:
  · 已有 docstring 的类**不动**(例如 T89 已写了实测对照表)
  · 只给没有任何说明的类插入;插入位置 = class 行之后、按 4 空格缩进
用法:python tools/add_model_notes.py [--dry-run]
"""
from __future__ import annotations

import os
import re
import sys

NOTES = {
    "igrf": (
        "来源:IGRF 国际地磁参考场球谐系数(1900-2030,含长期变化)。\n"
        "特性:纯内源场,平滑且精度高;**不含**磁层/尾电流等外部贡献,可与外部场模型相加使用。"
    ),
    "t96": (
        "来源:Tsyganenko 1996,以太阳风动压 Pdyn、Dst、IMF By/Bz 参数化。\n"
        "特性:外部场(不含偶极子,需另加内部场);含磁层顶与尾电流,适合 r 约 10 Re 以内的磁层位形。"
    ),
    "t01": (
        "来源:Tsyganenko 2001,在 T96 基础上区分平静与扰动条件。\n"
        "特性:外部场(不含偶极子);对亚暴/磁暴位形描述更真实,参数更多。"
    ),
    "t04": (
        "来源:Tsyganenko 2004(TS05 的前身),细分各电流系贡献。\n"
        "特性:外部场(不含偶极子);面向强扰动,计算量比 T96/T01 更大。"
    ),
    "ts05": (
        "来源:Tsyganenko & Sitnov 2005,多卫星数据拟合。\n"
        "特性:外部场(不含偶极子);磁暴期间表现最好,参数多、计算最重。"
    ),
    "ta16": (
        "来源:Tsyganenko & Andreeva 2016,含部分屏蔽与偶极倾角依赖。\n"
        "特性:外部场(不含偶极子);改进赤道面电流与倾角效应的描述。"
    ),
}


def find_class_line(text: str, node_type: str):
    """定位 type="X" 之后第一个 class 行的起止位置。"""
    m = re.search(r'type="' + re.escape(node_type) + r'"', text)
    if not m:
        return None
    m2 = re.search(r"^class\s+\w+.*?:\s*$", text[m.end():], re.M)
    if not m2:
        return None
    start = m.end() + m2.start()
    end = m.end() + m2.end()
    return start, end


def has_docstring(text: str, class_end: int) -> bool:
    tail = text[class_end:]
    for line in tail.splitlines():
        s = line.strip()
        if not s:
            continue
        return s.startswith('"""') or s.startswith("'''") or s.startswith('r"""')
    return False


def main() -> int:
    dry = "--dry-run" in sys.argv
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    nodes_dir = os.path.join(root, "nodes")
    done, skipped = [], []
    for node_type, note in NOTES.items():
        path = None
        for fn in sorted(os.listdir(nodes_dir)):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(nodes_dir, fn)
            with open(p, encoding="utf-8") as f:
                if f'type="{node_type}"' in f.read():
                    path = p
                    break
        if not path:
            skipped.append(f"{node_type}(未找到声明)")
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        pos = find_class_line(text, node_type)
        if not pos:
            skipped.append(f"{node_type}(未找到 class 行)")
            continue
        if has_docstring(text, pos[1]):
            skipped.append(f"{node_type}(已有说明,保留)")
            continue
        ins = "\n" + '    """' + note + '"""'   # 注意:pos[1] 是"class 行结束"的索引(整数),
                                                  # 这里要的是插入用的**文本**,不能拿它做字符串拼接
        new = text[:pos[1]] + ins + text[pos[1]:]
        if not dry:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(new)
        done.append(f"{node_type} -> {os.path.basename(path)}")
    print("已补说明:", ", ".join(done) if done else "(无)")
    print("跳过:", ", ".join(skipped) if skipped else "(无)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
