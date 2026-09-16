"""粒子度量插件系统(#43)—— 暂停态属性查看器的"物理量"这一半。

为什么要插件化:C++ 侧只该提供**原始快照**(位置/速度/荷质比/局部 B),
而"能量、俯仰角、损失锥、回旋半径、绝热不变量…"这类**派生量**属于分析口径,
会不断增长;把它们写成 `analysis/*.py` 里的纯函数插件,新增一个指标 = 丢一个文件,
C++ 与前端都不用改(面板按服务器返回的目录自动成表)。

插件写法(见 analysis/basic_metrics.py):

    @register_metric("energy_mev", title="能量", unit="MeV",
                     desc="相对论动能 (γ−1)mc²")
    def energy_mev(pos, vel, q, m, B):
        ...            # pos: Re(GSM)  vel: Re/s  q: 电荷数  m: 原子质量单位  B: nT
        return value   # 标量或短字符串

约定(C++ 快照给出的单位,与渲染/积分器内部一致):
    pos  位置,Re(GSM 类坐标)
    vel  速度,Re/s(物理速度 = vel × 6371 km/s)
    q    电荷数(质子 1、电子 −1、α 2)
    m    质量,原子质量单位
    B    局部磁感应强度矢量,nT
    status 0=存活 1=沉降 2=越界
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

_METRICS: dict[str, dict] = {}
_SCANNED: dict[str, float] = {}      # 文件路径 → mtime(增量热扫)
_DIRS: list[str] = []

# ---- 物理常数(与 C++ 侧一致)----
RE_KM = 6371.0
AMU_KG = 1.66053906660e-27
QE_C = 1.602176634e-19
C_KM_S = 299792.458
MEV_J = 1.602176634e-13
B_SURF_NT = 31200.0                  # 本项目场表的归一化基准(偶极赤道面)


def register_metric(name, *, title="", unit="", desc="", order=100):
    """注册一个粒子度量插件(纯函数)。order 决定面板里的显示顺序。"""
    def deco(fn):
        _METRICS[name] = {"name": name, "title": title or name, "unit": unit,
                          "desc": desc, "order": order, "fn": fn}
        return fn
    return deco


def load_metrics(root, extra_dirs=None):
    """热扫度量插件目录(默认 <root>/analysis 与 <root>/user_analysis)。

    与节点注册表同风格:**按文件路径 + 唯一模块名**加载(便于热重载),
    用 mtime 做增量扫描 —— 改了文件下次查询即生效,不用重启服务器。
    """
    global _DIRS
    dirs = [d for d in ((os.path.join(root, "analysis"),
                         os.path.join(root, "user_analysis"))
                        + tuple(extra_dirs or ())) if os.path.isdir(d)]
    _DIRS = dirs
    loaded = 0
    for d in dirs:
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            path = os.path.join(d, fn)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if _SCANNED.get(path) == mtime:
                continue
            mod_name = "_mfanalysis_" + os.path.splitext(fn)[0]
            try:
                spec = importlib.util.spec_from_file_location(mod_name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = module
                spec.loader.exec_module(module)
                _SCANNED[path] = mtime
                loaded += 1
            except Exception as e:                      # 单个插件坏掉不影响其它
                sys.stderr.write(f"[analysis] 插件加载失败 {path}: {e}\n")
    return loaded


def catalog():
    """度量目录(前端据此自动成表;新增插件无需改前端)。"""
    return [{k: v[k] for k in ("name", "title", "unit", "desc", "order")}
            for v in sorted(_METRICS.values(), key=lambda x: (x["order"], x["name"]))]


def _val(fn, item):
    import numpy as np
    pos = np.asarray(item["pos"], dtype=float)
    vel = np.asarray(item["vel"], dtype=float)
    b = np.asarray(item.get("b") or [0.0, 0.0, 0.0], dtype=float)
    try:
        v = fn(pos, vel, float(item.get("q", 1.0)), float(item.get("m", 1.0)), b)
    except Exception as e:
        return f"<{type(e).__name__}>"
    if isinstance(v, (int, float)):
        return float(v)
    return v


def analyze(payload_json: str) -> str:
    """入口:C++ 传快照 JSON,返回 {items:[{id, <指标>: 值…}], metrics:[目录]}。"""
    payload = json.loads(payload_json)
    root = payload.get("root") or "."
    if not _DIRS or payload.get("rescan", True):
        load_metrics(root)
    want = payload.get("metrics") or [m["name"] for m in catalog()]
    fns = [(n, _METRICS[n]["fn"]) for n in want if n in _METRICS]
    out = []
    for item in payload.get("items", []):
        # 原始快照字段**原样带上**(面板要显示位置/速度的 xyz 与球坐标;
        # 度量插件本身不需要关心这些)。此前漏掉 → 前端读 item.pos 抛异常。
        row = {k: item.get(k) for k in ("id", "pos", "vel", "q", "m", "status",
                                        "color", "b")}
        for name, fn in fns:
            row[name] = _val(fn, item)
        out.append(row)
    return json.dumps({"items": out, "metrics": catalog()}, ensure_ascii=False)
