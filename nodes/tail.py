"""远磁尾解析模型节点(Harris / Flaring Harris / Kan 1973)。

数学忠实移植自 legacy/python_bridge.py,含磁尾铰接(hinging)效应。
"""
from __future__ import annotations

import numpy as np

from engine import register_node, Node, Port, Param, Field


def _z_shift(ps, x):
    """铰接:近地随偶极倾角翘起,远尾被太阳风压平(legacy 同款公式)。"""
    Rc = 10.0
    return 0.5 * np.tan(ps) * (x + Rc - np.sqrt((x + Rc) ** 2 + 16.0))


@register_node(
    type="tail",
    name="远磁尾解析模型", category="磁场/远磁尾", icon="🌊",
    inputs={"kp": Port("scalar", default=2.0, min=0.0, max=9.0),
            "ps": Port("scalar", default=0.0)},
    outputs={"field": "vector_field"},
    params={"model": Param("enum", default="off",
                           choices=["off", "harris", "flaring", "kan"])},
)
class TailNode(Node):
    def compute(self, kp, ps):
        lat = self.lattice
        X, Y, Z = lat.mesh()
        model = self.params["model"]
        if model == "off":
            data = np.zeros((lat.nx, lat.ny, lat.nz, 3), dtype=np.float64)
            return {"field": Field("vector", data, lat)}

        B00 = 30.0 + kp * 5.0
        Bz0 = 1.5 + kp * 0.3
        L0 = 1.5
        z_eff = Z - _z_shift(ps, X)

        if model == "harris":
            bx = B00 * np.tanh(z_eff / L0)
        else:  # flaring / kan(legacy 中二者同式)
            xt = np.clip(-X, 0.0, None)
            xt_rel = xt / 15.0
            L_x = L0 * (1.0 + xt_rel ** 0.6)
            B0_x = B00 / (1.0 + xt_rel ** 0.5)
            bx = B0_x * np.tanh(z_eff / L_x)
        by = np.zeros_like(X)
        bz = np.full_like(X, Bz0)
        return {"field": Field.vector(bx, by, bz, lat)}
