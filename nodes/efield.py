"""电场节点:对流+共转 / Volland-Stern(含屏蔽)。

与旧 C++ 热路径不同,电场在新架构中烘焙为格点表(REFACTOR_PLAN §2):
Boris 积分器直接查表。E_corot 依赖 B 场 → 电场节点消费 B 场端口,
这就是"动态链接数据"的示范用例。

单位约定:B 端口为物理 nT;本节点输出为**仿真归一化单位**
(与旧引擎热路径一致):E_conv 常量 5e-6×倍率,共转项 -(Ω×r)×(B/31200),
即 B 以 dipole_moment=1 的归一化标度参与计算。
"""
from __future__ import annotations

import numpy as np

from engine import register_node, Node, Port, Param, Field

_OMEGA = 7.27e-5       # 地球自转角速度(归一化单位)
_B_SCALE = 1.0 / 31200.0  # nT → 归一化单位(与旧引擎 get_field 的 scale_factor 一致)


def _corotation(b_data, X, Y, Z):
    """E_corot = -(Ω×r)×B,Ω=(0,0,_OMEGA),B 以归一化单位参与。"""
    vx = -_OMEGA * Y
    vy = _OMEGA * X
    bx = b_data[..., 0] * _B_SCALE
    by = b_data[..., 1] * _B_SCALE
    bz = b_data[..., 2] * _B_SCALE
    # v × B
    ex = vy * bz
    ey = -vx * bz
    ez = vx * by - vy * bx
    return -ex, -ey, -ez


@register_node(
    type="convection_corotation",
    name="对流+共转电场", category="电场", icon="⚡",
    inputs={"b": Port("vector_field")},
    outputs={"field": "vector_field"},
    params={"multiplier": Param("scalar", default=1.0, min=1.0, max=100.0)},
)
class ConvectionCorotationNode(Node):
    """E = 晨昏对流(常数)+ 共转。与旧引擎 efield_model=0 同式。"""

    def compute(self, b):
        X, Y, Z = self.lattice.mesh()
        ecx, ecy, ecz = _corotation(b.data, X, Y, Z)
        e_conv = 5.0e-6 * self.params["multiplier"]
        return {"field": Field.vector(ecx, ecy + e_conv, ecz, self.lattice)}


@register_node(
    type="volland_stern",
    name="Volland-Stern(含屏蔽)", category="电场", icon="⚡",
    inputs={"b": Port("vector_field")},
    outputs={"field": "vector_field"},
    params={"multiplier": Param("scalar", default=1.0, min=1.0, max=100.0)},
)
class VollandSternNode(Node):
    """对流电场在 r<4 Re 内按 (r/4)² 屏蔽,与旧引擎 efield_model=1 同式。"""

    def compute(self, b):
        X, Y, Z = self.lattice.mesh()
        ecx, ecy, ecz = _corotation(b.data, X, Y, Z)
        r = np.sqrt(X ** 2 + Y ** 2 + Z ** 2)
        shielding = np.where((r < 4.0) & (r > 0.1), (r / 4.0) ** 2, 1.0)
        e_conv = 5.0e-6 * self.params["multiplier"] * shielding
        return {"field": Field.vector(ecx, ecy + e_conv, ecz, self.lattice)}
