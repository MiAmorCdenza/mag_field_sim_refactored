"""电场节点:对流+共转 / Volland-Stern(含屏蔽)。

与旧 C++ 热路径不同,电场在新架构中烘焙为格点表(REFACTOR_PLAN §2):
Boris 积分器直接查表。E_corot 依赖 B 场 → 电场节点消费 B 场端口,
这就是"动态链接数据"的示范用例。
"""
from __future__ import annotations

import numpy as np

from engine import register_node, Node, Port, Param, Field

_OMEGA = 7.27e-5  # 地球自转角速度(归一化单位)


def _corotation(b_data, X, Y, Z):
    """E_corot = -(Ω×r)×B,Ω=(0,0,_OMEGA)。"""
    vx = -_OMEGA * Y
    vy = _OMEGA * X
    bx, by, bz = b_data[..., 0], b_data[..., 1], b_data[..., 2]
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
