"""引力场节点:输出引力加速度矢量场(Boris 步进查表用,亦可解析兜底)。

与旧引擎 boris_step 中的引力项同式:g = -GM·r̂/r²,GM = 1.5398e-6 × 倍率。
"""
from __future__ import annotations

import numpy as np

from engine import register_node, Node, Port, Param, Field

_GM = 1.5398e-6


@register_node(
    type="gravity",
    name="地球引力场", category="物理", icon="🪐",
    inputs={},
    outputs={"field": "vector_field"},
    params={"multiplier": Param("scalar", default=1.0, min=1.0, max=1.0e5)},
)
class GravityNode(Node):
    def compute(self):
        X, Y, Z = self.lattice.mesh()
        r2 = X ** 2 + Y ** 2 + Z ** 2
        r = np.sqrt(r2)
        factor = np.where(r > 0.1, -_GM * self.params["multiplier"] / r ** 3, 0.0)
        return {"field": Field.vector(factor * X, factor * Y, factor * Z,
                                      self.lattice)}
