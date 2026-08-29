"""插件注册表:一个 .py = 一个节点类型(DSH 万物皆插件模式)。

- @register_node(**meta) 装饰器登记节点类
- Registry.scan() 扫描插件目录(nodes/ + user_nodes/),动态加载
- 每类型保留 current + previous(热重载回滚用)
- user_nodes/ 中同名 type 覆盖内置插件
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys

# 装饰器执行期间的暂存区:type -> (class, 源文件)
_REGISTERED = {}


def register_node(**meta):
    """注册节点插件。meta 见 REFACTOR_PLAN §5.2 完整字段。"""
    frame = inspect.currentframe().f_back
    src_file = frame.f_globals.get("__file__")

    def deco(cls):
        spec = dict(meta)
        spec.setdefault("inputs", {})
        spec.setdefault("outputs", {})
        spec.setdefault("params", {})
        spec.setdefault("name", meta.get("type"))
        spec.setdefault("category", "")
        spec.setdefault("domain", "field")
        spec.setdefault("impl", "python")
        spec.setdefault("cost", "cheap")
        spec.setdefault("icon", "⬡")
        spec.setdefault("version", 1)
        cls._node_spec = spec
        _REGISTERED[meta["type"]] = (cls, src_file)
        return cls

    return deco


class Registry:
    def __init__(self, plugin_dirs):
        self.plugin_dirs = [os.path.abspath(d) for d in plugin_dirs]
        self.nodes = {}      # type -> class(当前版)
        self.previous = {}   # type -> class(上一版,热重载回滚)
        self._sources = {}   # type -> 源文件路径

    # ---- 扫描与加载 ----
    def scan(self):
        """扫描所有插件目录,加载/刷新节点类型。"""
        for d in self.plugin_dirs:
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if not fn.endswith(".py") or fn.startswith("_"):
                    continue
                path = os.path.join(d, fn)
                mod_name = f"_mfplugin_{os.path.basename(d)}_{fn[:-3]}"
                spec = importlib.util.spec_from_file_location(mod_name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception as exc:  # 坏插件不拖垮引擎
                    from . import logging as engine_log
                    engine_log.log("engine.registry", "plugin_load_failed", "warn",
                                   f"插件加载失败: {path}", error=str(exc))
        for t, (cls, src) in _REGISTERED.items():
            if self.nodes.get(t) is not cls:
                if t in self.nodes:
                    self.previous[t] = self.nodes[t]
                self.nodes[t] = cls
                self._sources[t] = src

    def reload_type(self, node_type):
        """热重载单一类型(阶段 4 接入 watchdog)。"""
        src = self._sources.get(node_type)
        if not src or not os.path.exists(src):
            return False
        mod_name = f"_mfplugin_{os.path.basename(os.path.dirname(src))}_{os.path.basename(src)[:-3]}"
        # 不用 importlib.reload:Python 3.14 起 reload 会经 meta_path 重新
        # find_spec,而 _mfplugin_* 是合成名,PathFinder 按文件名找不到,
        # 必然抛 "spec not found"。与 scan() 一致:spec + exec_module。
        spec = importlib.util.spec_from_file_location(mod_name, src)
        if spec is None:
            return False
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        self.scan()
        return True

    # ---- 查询 ----
    def get(self, node_type):
        return self.nodes.get(node_type)

    def list_types(self):
        return sorted(self.nodes)

    def describe(self):
        """节点面板数据(前端编辑器用)。"""
        out = []
        for t, cls in sorted(self.nodes.items()):
            s = cls._node_spec
            out.append({
                "type": t,
                "name": s.get("name", t),
                "category": s.get("category", ""),
                "domain": s.get("domain", "field"),
                "impl": s.get("impl", "python"),
                "cost": s.get("cost", "cheap"),
                "icon": s.get("icon", ""),
                "version": s.get("version", 1),
                "inputs": {k: v.to_json() for k, v in s["inputs"].items()},
                "outputs": dict(s["outputs"]),
                "params": {k: v.to_json() for k, v in s["params"].items()},
            })
        return out


# 默认注册表(懒初始化:扫描 nodes/ 与 user_nodes/)
_DEFAULT = None


def default_registry(plugin_dirs=None):
    global _DEFAULT
    if _DEFAULT is None:
        if plugin_dirs is None:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            plugin_dirs = [os.path.join(root, "nodes"),
                           os.path.join(root, "user_nodes")]
        _DEFAULT = Registry(plugin_dirs)
        _DEFAULT.scan()
    return _DEFAULT
