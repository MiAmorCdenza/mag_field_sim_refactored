"""A2000(抛物面/CPMOD)模型的 DLL 加载器 —— 供 `paraboloid` 与 `tilt_source` 共用。

为什么单独一个文件:节点是**按文件路径 + 唯一模块名**加载的(为了热重载),
彼此之间无法用模块名互相 import。而 DLL 句柄必须**进程内只加载一次**,
所以放在一个正常可导入的共享模块里(仓库根在 sys.path 上 → `nodes._a2000_dll`)。

⚠ 本文件属于"引擎级"代码:改了它需要**重启服务器**才生效(节点文件才热重载)。
"""
from __future__ import annotations

import ctypes
import os

_MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
_LIB = None            # ctypes 句柄(进程内只加载一次)
_LIB_ERR = None


def _load_lib():
    """加载 A2000 DLL(带 gfortran 运行库目录);失败时给出可执行的修复提示。"""
    global _LIB, _LIB_ERR
    if _LIB is not None or _LIB_ERR is not None:
        return _LIB
    dll = os.path.join(_MODELS_DIR, "a2000.dll")
    if not os.path.exists(dll):
        _LIB_ERR = (f"缺少 {dll}:先运行 scripts\\build_a2000.ps1 编译"
                    f"(需要 64 位 gfortran)")
        return None
    try:
        os.add_dll_directory(_MODELS_DIR)      # gfortran 运行库就在旁边
        lib = ctypes.CDLL(dll)
        D, P, I = ctypes.c_double, ctypes.POINTER(ctypes.c_double), ctypes.c_int
        lib.a2000_set_time.argtypes = [D, I, I, I]
        lib.a2000_params.argtypes = [D, D, P, D, D, P, ctypes.POINTER(I)]
        lib.a2000_field.argtypes = [P, P, P, P]
        lib.a2000_batch.argtypes = [P, I, P, P, P]
        lib.a2000_set_sources.argtypes = [D] * 7
        lib.a2000_tilt.argtypes = [D, I, I, I, P, P]   # 日期 → 倾角(同一份 TRANS)
        lib.a2000_set_sources(1, 1, 1, 1, 1, 1, 1)     # 官方"全开"初始化
        _LIB = lib
    except OSError as e:
        _LIB_ERR = f"加载 a2000.dll 失败:{e}"
        return None
    return _LIB


class _StdoutSilencer:
    """临时把进程 fd 1 指向空设备。

    模型内部有若干 PRINT(贝塞尔函数的异常分支会打印),逐点调用会刷爆服务器
    日志 —— 磁盘 fd 级屏蔽比改源码更干净(源码保持与官方一致)。
    """

    def __enter__(self):
        self._saved = os.dup(1)
        self._null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(self._null, 1)
        return self

    def __exit__(self, *exc):
        os.dup2(self._saved, 1)
        os.close(self._null)
        os.close(self._saved)
        return False
