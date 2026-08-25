"""点阵(Lattice):非均匀拉伸轴 + 惰性网格缓存。

由旧版 python_bridge._make_stretched_axis 泛化而来。
设计(REFACTOR_PLAN §4.3):
- Field 自带 lattice 引用;v1 图中所有节点共用一张点阵
- z 轴细预设:±10 Re 内 0.2 Re,覆盖整条磁尾电流片
- 缓存键包含 lattice:换点阵预设自动标脏
"""
from __future__ import annotations

import numpy as np


def stretched_axis(vmin, vmax, vcenter, inner_halfwidth, inner_dx,
                   total_points, power=1.8):
    """非均匀轴:中心区均匀细网格,外部幂律拉伸(近处密、远处疏)。

    返回严格升序、去重后的 float64 数组。
    """
    inner = np.arange(max(vmin, vcenter - inner_halfwidth),
                      min(vmax, vcenter + inner_halfwidth) + inner_dx * 0.5,
                      inner_dx)
    span_left = inner[0] - vmin
    span_right = vmax - inner[-1]
    n_outer = max(0, total_points - len(inner))

    if n_outer <= 0 or (span_left + span_right) <= 0.0:
        return np.unique(inner)

    n_left = max(1, int(n_outer * span_left / (span_left + span_right)))
    n_right = max(1, n_outer - n_left)

    def _side(start, end, n):
        if n <= 0:
            return np.array([])
        span = end - start
        if span <= 0.0:
            return np.array([])
        t = np.linspace(0.0, 1.0, n)
        return start + span * t ** power

    left = _side(inner[0], vmin, n_left)
    right = _side(inner[-1], vmax, n_right)
    return np.unique(np.concatenate([left, inner, right]))


# 轴预设:参数透传给 stretched_axis
AXIS_PRESETS = {
    # ---- 与旧版一致的粗轴(诊断点对照用)----
    "x_coarse": dict(vmin=-90.0, vmax=25.0, vcenter=0.0,
                     inner_halfwidth=3.0, inner_dx=0.1, total_points=80),
    "y_coarse": dict(vmin=-45.0, vmax=45.0, vcenter=0.0,
                     inner_halfwidth=3.0, inner_dx=0.1, total_points=72),
    "z_coarse": dict(vmin=-45.0, vmax=45.0, vcenter=0.0,
                     inner_halfwidth=3.0, inner_dx=0.1, total_points=72),
    # ---- 细轴 ----
    "x_fine": dict(vmin=-90.0, vmax=25.0, vcenter=0.0,
                   inner_halfwidth=3.0, inner_dx=0.1, total_points=128),
    "y_fine": dict(vmin=-45.0, vmax=45.0, vcenter=0.0,
                   inner_halfwidth=3.0, inner_dx=0.1, total_points=96),
    # z 轴:±10 Re 内 0.2 Re,覆盖整条磁尾电流片
    "z_fine": dict(vmin=-45.0, vmax=45.0, vcenter=0.0,
                   inner_halfwidth=10.0, inner_dx=0.2, total_points=128),
}

# 点阵预设:名字 -> {x/y/z: 轴预设名}
LATTICE_PRESETS = {
    "legacy": dict(x="x_coarse", y="y_coarse", z="z_coarse"),
    "coarse": dict(x="x_coarse", y="y_coarse", z="z_coarse"),
    "fine":   dict(x="x_fine", y="y_fine", z="z_fine"),
}


class Lattice:
    """三维采样点阵。"""

    def __init__(self, xs, ys, zs, name=None):
        self.xs = np.asarray(xs, dtype=np.float64)
        self.ys = np.asarray(ys, dtype=np.float64)
        self.zs = np.asarray(zs, dtype=np.float64)
        self.name = name
        self._mesh = None

    # ---- 基本属性 ----
    @property
    def nx(self):
        return len(self.xs)

    @property
    def ny(self):
        return len(self.ys)

    @property
    def nz(self):
        return len(self.zs)

    @property
    def shape(self):
        return (self.nx, self.ny, self.nz)

    @property
    def size(self):
        return self.nx * self.ny * self.nz

    def mesh(self):
        """惰性生成 meshgrid(indexing='ij'),供逐格点向量化计算。"""
        if self._mesh is None:
            self._mesh = np.meshgrid(self.xs, self.ys, self.zs, indexing="ij")
        return self._mesh

    # ---- 构造 ----
    @classmethod
    def from_preset(cls, name="fine"):
        axes = LATTICE_PRESETS[name]
        xs = stretched_axis(**AXIS_PRESETS[axes["x"]])
        ys = stretched_axis(**AXIS_PRESETS[axes["y"]])
        zs = stretched_axis(**AXIS_PRESETS[axes["z"]])
        return cls(xs, ys, zs, name=name)

    @classmethod
    def from_json(cls, doc):
        if not doc:
            return None
        if "preset" in doc:
            return cls.from_preset(doc["preset"])
        return cls(doc["xs"], doc["ys"], doc["zs"])

    def to_json(self):
        # 仅已知预设名可用名字表达;自定义点阵显式输出轴
        if self.name and self.name in LATTICE_PRESETS:
            return {"preset": self.name}
        return {"xs": self.xs.tolist(), "ys": self.ys.tolist(),
                "zs": self.zs.tolist()}

    def __repr__(self):
        return (f"<Lattice name={self.name!r} "
                f"nx={self.nx} ny={self.ny} nz={self.nz} "
                f"cells={self.size}>")
