"""格点场 Field:图里流动的核心数据类型。

- kind: "vector"(shape (nx,ny,nz,3))| "scalar"(shape (nx,ny,nz))
- id:   单调递增版本号(图级分配),是内容寻址缓存的关键
- lattice: 点阵引用(v1 与图共享;数据结构已支持字段级点阵,
  节点级点阵 + 自动重采样为后续优化,见 REFACTOR_PLAN §4.3)
"""
from __future__ import annotations

import numpy as np


class Field:
    __slots__ = ("kind", "data", "id", "lattice")

    def __init__(self, kind, data, lattice, field_id=None):
        if kind not in ("vector", "scalar"):
            raise ValueError(f"未知场类型: {kind}")
        self.kind = kind
        self.data = np.asarray(data, dtype=np.float64)
        self.id = field_id
        self.lattice = lattice

    # ---- 工厂 ----
    @staticmethod
    def vector(bx, by, bz, lattice, field_id=None):
        """由三个分量数组构造矢量场(分量形状 = lattice.shape)。"""
        data = np.stack([np.asarray(bx, dtype=np.float64),
                         np.asarray(by, dtype=np.float64),
                         np.asarray(bz, dtype=np.float64)], axis=-1)
        return Field("vector", data, lattice, field_id=field_id)

    @staticmethod
    def scalar(values, lattice, field_id=None):
        return Field("scalar", values, lattice, field_id=field_id)

    # ---- 查询 ----
    @property
    def shape(self):
        return self.data.shape

    def is_finite(self):
        return bool(np.isfinite(self.data).all())

    def magnitude(self):
        """矢量场模长(标量数组)。"""
        if self.kind != "vector":
            raise TypeError("magnitude 仅对矢量场有效")
        return np.sqrt(np.sum(self.data ** 2, axis=-1))

    def __repr__(self):
        return (f"<Field {self.kind} shape={self.data.shape} "
                f"id={self.id} lattice={getattr(self.lattice, 'name', None)!r}>")
