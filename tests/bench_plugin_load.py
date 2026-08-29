"""插件加载耗时基准:Python 模块(注册表扫描路径)vs importlib.reload。

对照:
  1) spec_from_file_location + exec_module(Registry.scan 的实际路径)
  2) importlib.reload(热重载路径,固定模块对象)
  3) compile(AST→字节码,不含执行)
运行: python tests/bench_plugin_load.py
"""
import importlib
import importlib.util
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PLUGIN_PATH = os.path.join(ROOT, "nodes", "combine.py")


def bench(fn, n=100, name=""):
    for _ in range(5):
        fn()  # 预热(numpy 等已载)
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    dt = (time.perf_counter() - t0) / n * 1000
    print(f"  {name}: {dt:.3f} ms/次")


# 1) 注册表扫描路径:每次全新模块名(近似热加载新文件)
_counter = [0]


def scan_load():
    _counter[0] += 1
    mod_name = f"_bench_plugin_{_counter[0]}"
    spec = importlib.util.spec_from_file_location(mod_name, PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


# 2) reload 路径:固定模块对象(热重载语义)。
# Python 3.14 起 reload 会经 meta_path 重新 find_spec,因此模块名必须
# 能被 PathFinder 按文件名重新定位 —— 用一个真实导入的独立插件文件。
_RELOAD_PLUGIN = os.path.join(ROOT, "tests", "_bench_plugin_reloadable.py")
_RELOAD_DIR = os.path.dirname(_RELOAD_PLUGIN)
if _RELOAD_DIR not in sys.path:
    sys.path.insert(0, _RELOAD_DIR)

import _bench_plugin_reloadable as _stable  # noqa: E402


def reload_path():
    importlib.reload(_stable)


# 3) 仅编译
with open(PLUGIN_PATH, encoding="utf-8") as f:
    SRC = f.read()


def parse_compile():
    compile(SRC, "combine.py", "exec")


print("插件加载耗时(numpy 已预热):")
bench(scan_load, name="exec_module(注册表扫描路径)")
bench(reload_path, name="importlib.reload(热重载路径)")
bench(parse_compile, name="compile(AST→字节码,不含执行)")
print(f"combine.py 大小: {len(SRC)} 字节")
