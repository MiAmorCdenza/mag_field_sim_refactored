"""电场节点:原子场 + 图内显式组合(不内部复合)。

设计原则(与 B 场链一致):每个节点只输出一种独立的力场,
组合通过图连线完成——"原子节点 + 显式组合"。

    E = add( corotation(B), mul( convection, volland_shield ) )
        ├── convection      晨昏对流(常数场,倍率参数)
        ├── corotation      共转电场 -(Ω×r)×B(消费 B 场端口)
        └── volland_shield  屏蔽系数标量场((r/r0)² 内屏蔽,可调 r0)

单位约定:B 端口为物理 nT;本节点族输出**仿真归一化单位**
(与旧引擎热路径一致):E_conv 常量 5e-6×倍率,共转项 -(Ω×r)×(B/31200)。
"""
from __future__ import annotations

import numpy as np

from engine import register_node, Node, Port, Param, Field

_OMEGA = 7.27e-5       # 地球自转角速度(归一化单位)
_B_SCALE = 1.0 / 31200.0  # nT → 归一化单位(与旧引擎 get_field 的 scale_factor 一致)


@register_node(
    type="convection",
    name="晨昏对流电场", category="电场", icon="⚡",
    inputs={},
    outputs={"field": "vector_field"},
    params={"multiplier": Param("scalar", default=1.0, min=1.0, max=100.0)},
)
class ConvectionNode(Node):
    """晨昏对流电场:常数矢量场(0, 5e-6×倍率, 0),归一化单位。"""

    def compute(self):
        lat = self.lattice
        data = np.zeros((lat.nx, lat.ny, lat.nz, 3), dtype=np.float64)
        data[..., 1] = 5.0e-6 * self.params["multiplier"]
        return {"field": Field("vector", data, lat)}


@register_node(
    type="corotation",
    name="共转电场", category="电场", icon="🔄",
    inputs={"b": Port("vector_field")},
    outputs={"field": "vector_field"},
)
class CorotationNode(Node):
    """共转电场 E = -(Ω×r)×B,消费 B 场端口(动态链接数据示范)。"""

    def compute(self, b):
        X, Y, Z = self.lattice.mesh()
        vx = -_OMEGA * Y
        vy = _OMEGA * X
        bx = b.data[..., 0] * _B_SCALE
        by = b.data[..., 1] * _B_SCALE
        bz = b.data[..., 2] * _B_SCALE
        ex = vy * bz
        ey = -vx * bz
        ez = vx * by - vy * bx
        return {"field": Field.vector(-ex, -ey, -ez, self.lattice)}


@register_node(
    type="volland_shield",
    name="Volland-Stern 屏蔽系数", category="电场", icon="🛡",
    inputs={},
    outputs={"coef": "scalar_field"},
    params={"r0": Param("scalar", default=4.0, min=1.0, max=10.0)},
)
class VollandShieldNode(Node):
    """屏蔽系数标量场:r<r0 内 (r/r0)² 指数削弱,外部为 1。

    与 convection 相乘(mul 节点)即得 Volland-Stern 屏蔽对流场;
    与 corotation 相加(add 节点)得到完整屏蔽电场。
    """

    def compute(self):
        X, Y, Z = self.lattice.mesh()
        r = np.sqrt(X ** 2 + Y ** 2 + Z ** 2)
        r0 = self.params["r0"]
        w = np.where((r < r0) & (r > 0.1), (r / r0) ** 2, 1.0)
        return {"coef": Field("scalar", w, self.lattice)}
