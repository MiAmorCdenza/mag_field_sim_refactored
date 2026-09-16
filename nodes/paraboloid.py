"""A2000(抛物面 / CPMOD 家族)内磁场节点 —— 偶极子的升级版。

物理:把磁层磁场写成**电流源的叠加** ——
    偶极 + 环电流 + 磁尾电流 + 磁层顶 CF 屏蔽(偶极/环电流两项)+ Region-1 FAC
    + 穿透 IMF;由经验参数驱动:**Dst 决定环电流强度**(BR = Dst − 10),
    AL 决定尾瓣磁通,太阳风动压 + IMF Bz 决定磁层顶驻点 R1 与 FAC 强度。
    内磁层因此比纯偶极真实得多(磁暴期间环电流会压低赤道场)。

来源与验证(重要):
  · 源码 = **IRBEM 的标准双精度实现** `models/a2000_irbem.f`
    (IRBEM-lib / Alexeev & Kalegaev;本机 SpacePy 自带,另有作者组官网
     http://www.magnetosphere.ru/ 与 PRBEM/IRBEM 仓库)
  · `models/a2000_api.f90` 是两段式 C 包装:submod(参数,每图一次)→ A_field(逐点)
  · 编译见 `scripts/build_a2000.ps1`(需 64 位 gfortran)
  · 已验:参数映射与作者组在线工具(earth3d)**逐项吻合**(R1/R2/BR/AJ0 差 <0.3%);
    总场与解析偶极差 0.03%;Dst 0→−150 时赤道内区总场单调下降(环电流生效);
    批量 ~10 µs/点(114k 点 ≈1 s)
  · 未采用:模型给出的 7 个分源行 —— 该 IRBEM 变体里它们的内部归一化与
    `PSTATUS` 开关对总场无影响,量级也对不上,故只输出**总场**;
    分源/开关留作 TODO(等读透 FIELD 里的 bd0/bka 归一化再说)

注意(源码自带警告):抛物面坐标在 **Ox 轴**(y=z=0)奇异,那里会返回 NaN ——
本节点把靠轴的格点沿 ρ 轻推一个极小量,避免整张表被污染。
"""
from __future__ import annotations

import ctypes
import os

import numpy as np

from engine import register_node, Node, Port, Param, Field, GraphError

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "models")
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
        lib.a2000_set_sources(1, 1, 1, 1, 1, 1, 1)   # 官方"全开"初始化
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


@register_node(
    type="paraboloid",
    name="A2000 抛物面(内场)", category="磁场/内部场", icon="🧭",
    cost="expensive",
    inputs={
        "dst": Port("scalar", default=-30.0,
                    desc="Dst 指数 nT(决定环电流强度:BR = Dst − 10)"),
        "rho": Port("scalar", default=5.0, min=0.1,
                    desc="太阳风密度 cm⁻³"),
        "v": Port("scalar", default=400.0, min=50.0,
                  desc="太阳风速度 km/s"),
        "al": Port("scalar", default=-100.0,
                   desc="AL 指数 nT(决定尾瓣磁通;必须为负)"),
        "by": Port("scalar", default=0.0, desc="IMF By nT(GSM)"),
        "bz": Port("scalar", default=-2.0, desc="IMF Bz nT(GSM)"),
    },
    outputs={"field": "vector_field"},
    params={
        "year": Param("int", default=2026, min=1901, max=2099,
                      desc="日期 → 偶极倾角(与 IGRF 高斯系数)"),
        "month": Param("int", default=9, min=1, max=12),
        "day": Param("int", default=16, min=1, max=31),
        "ut": Param("scalar", default=1.0, min=0.0, max=24.0,
                    desc="UT 小时(含小数)"),
    },
    version=1,
)
class ParaboloidNode(Node):
    """A2000 内磁场(偶极 + 环电流 + 尾 + 屏蔽 + FAC + 穿透 IMF)。

    输出的是**内磁层总场**(含偶极)⇒ 直接替代 `偶极子` 节点,不要再叠加 dipole;
    与外部模型(T89 等)组合时注意:本模型**已含尾电流/磁层顶电流**,
    与 T89 相加会重复计,推荐单独使用或只叠加均匀 IMF。
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.last_par = None      # 最近一次的 par(1..10),便于测试/诊断读数

    def compute(self, dst, rho, v, al, by, bz):
        lib = _load_lib()
        if lib is None:
            raise GraphError(_LIB_ERR)
        if al >= 0.0:
            raise GraphError("AL 必须为负(尾瓣磁通用 BT = −AL/7,非负会让磁通反向)")
        X, Y, Z = self.lattice.mesh()
        shape = X.shape
        pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1).astype(np.float64)
        # Ox 轴奇异:ρ = sqrt(y²+z²) 近零的点沿 y 轻推(0.02 Re ≪ 格距,不改变物理)
        rho_cyl = np.hypot(pts[:, 1], pts[:, 2])
        near_axis = rho_cyl < 0.02
        if near_axis.any():
            pts[near_axis, 1] = np.where(np.abs(pts[near_axis, 2]) > 0,
                                         0.02, 0.02)
            pts[near_axis, 2] = np.where(np.abs(pts[near_axis, 2]) > 0,
                                         0.0, 0.0)
        n = pts.shape[0]
        P = ctypes.POINTER(ctypes.c_double)
        bimf = np.array([0.0, by, bz], dtype=np.float64)
        par = np.zeros(10, dtype=np.float64)
        ifail = ctypes.c_int(0)
        with _StdoutSilencer():
            lib.a2000_set_time(float(self.params["ut"]), int(self.params["year"]),
                               int(self.params["month"]), int(self.params["day"]))
            lib.a2000_params(float(rho), float(v), bimf.ctypes.data_as(P),
                             float(dst), float(al), par.ctypes.data_as(P),
                             ctypes.byref(ifail))
            if ifail.value != 0:
                raise GraphError(f"A2000 参数非法(ifail={ifail.value}):"
                                 f"检查 ρ>0、V>0")
            bm = np.zeros((n, 3), dtype=np.float64)
            bb = np.zeros((7, n, 3), dtype=np.float64)
            lib.a2000_batch(par.ctypes.data_as(P), n, pts.ctypes.data_as(P),
                            bm.ctypes.data_as(P), bb.ctypes.data_as(P))
        self.last_par = par.copy()
        if not np.all(np.isfinite(bm)):
            bad = int(np.sum(~np.isfinite(bm)))
            raise GraphError(f"A2000 返回 {bad}/{n} 个非有限值:"
                             f"检查是否落在 Ox 轴奇异区附近")
        bx = bm[:, 0].reshape(shape)
        by_ = bm[:, 1].reshape(shape)
        bz_ = bm[:, 2].reshape(shape)
        return {"field": Field.vector(bx, by_, bz_, self.lattice)}
