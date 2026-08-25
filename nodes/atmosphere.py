"""大气阻尼节点:输出阻力系数标量场(Boris 步进查表用)。

与旧引擎 boris_step 中的大气分支同式(单层指数 / 分层模型)。
"""
from __future__ import annotations

import numpy as np

from engine import register_node, Node, Port, Param, Field


@register_node(
    type="drag_single",
    name="大气阻尼(单层指数)", category="大气", icon="🌫",
    inputs={},
    outputs={"coef": "scalar_field"},
    params={"multiplier": Param("scalar", default=1.0, min=1.0, max=100.0)},
)
class DragSingleNode(Node):
    def compute(self):
        X, Y, Z = self.lattice.mesh()
        r = np.sqrt(X ** 2 + Y ** 2 + Z ** 2)
        nu = np.where((r < 1.15) & (r > 0.0),
                      100.0 * self.params["multiplier"] * np.exp(-(r - 1.0) / 0.01),
                      0.0)
        return {"coef": Field("scalar", nu, self.lattice)}


@register_node(
    type="drag_layered",
    name="大气阻尼(分层模型)", category="大气", icon="🌫",
    inputs={},
    outputs={"coef": "scalar_field"},
    params={"multiplier": Param("scalar", default=1.0, min=1.0, max=100.0)},
)
class DragLayeredNode(Node):
    def compute(self):
        X, Y, Z = self.lattice.mesh()
        r = np.sqrt(X ** 2 + Y ** 2 + Z ** 2)
        h = (r - 1.0) * 6371.0  # km
        nu = np.zeros_like(r)
        m = self.params["multiplier"]
        nu = np.where(h < 100.0, 1000.0 * np.exp(-h / 8.0), nu)
        nu = np.where((h >= 100.0) & (h < 500.0), 10.0 * np.exp(-(h - 100.0) / 40.0), nu)
        nu = np.where(h >= 500.0, 0.5 * np.exp(-(h - 500.0) / 100.0), nu)
        nu = nu * m
        nu = np.where((r < 1.15) & (r > 0.0), nu, 0.0)
        return {"coef": Field("scalar", nu, self.lattice)}
