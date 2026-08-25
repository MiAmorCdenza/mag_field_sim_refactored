"""组合节点:add / mul / blend / mask / resample(REFACTOR_PLAN §5.11)。"""
from __future__ import annotations

import numpy as np

from engine import register_node, Node, Port, Param, Field
from engine.lattice import Lattice


@register_node(
    type="add",
    name="加法", category="组合", icon="➕",
    inputs={"a": Port("vector_field"), "b": Port("vector_field")},
    outputs={"field": "vector_field"},
)
class AddNode(Node):
    def compute(self, a, b):
        return {"field": a.data + b.data}


@register_node(
    type="mul",
    name="乘法(逐格点)", category="组合", icon="✖",
    inputs={"a": Port("vector_field"), "w": Port("scalar_field")},
    outputs={"field": "vector_field"},
)
class MulNode(Node):
    """矢量场 × 标量场(标量源由引擎广播为标量场)。"""

    def compute(self, a, w):
        return {"field": a.data * w.data[..., None]}


@register_node(
    type="blend",
    name="权重混合", category="组合", icon="🌗",
    inputs={"a": Port("vector_field"), "b": Port("vector_field"),
            "w": Port("scalar_field")},
    outputs={"field": "vector_field"},
)
class BlendNode(Node):
    """w·a + (1-w)·b,w 可为标量场或标量(引擎广播)。"""

    def compute(self, a, b, w):
        ww = w.data[..., None]
        return {"field": ww * a.data + (1.0 - ww) * b.data}


@register_node(
    type="mask",
    name="区域掩码", category="组合", icon="🎭",
    inputs={},
    outputs={"weight": "scalar_field"},
    params={"region": Param("enum", default="dayside",
                            choices=["dayside", "nightside", "sphere", "shell"]),
            "r0": Param("scalar", default=10.0),
            "r1": Param("scalar", default=20.0)},
)
class MaskNode(Node):
    """输出标量权重场(0/1),与 mul/blend 组合实现空间调制。"""

    def compute(self):
        X, Y, Z = self.lattice.mesh()
        r = np.sqrt(X ** 2 + Y ** 2 + Z ** 2)
        region = self.params["region"]
        if region == "dayside":
            w = (X > -10.0).astype(np.float64)
        elif region == "nightside":
            w = (X <= -10.0).astype(np.float64)
        elif region == "sphere":
            w = (r < self.params["r0"]).astype(np.float64)
        else:  # shell
            r0, r1 = self.params["r0"], self.params["r1"]
            w = ((r >= min(r0, r1)) & (r < max(r0, r1))).astype(np.float64)
        return {"weight": Field("scalar", w, self.lattice)}


@register_node(
    type="resample",
    name="重采样", category="组合", icon="🔁",
    inputs={"field": Port("vector_field")},
    outputs={"field": "vector_field"},
    params={"preset": Param("enum", default="fine",
                            choices=["legacy", "coarse", "fine"])},
)
class ResampleNode(Node):
    """点阵转换(scipy 三线性)。目标点阵与图点阵不同时,
    下游节点仍需同图点阵(v1 图级单点阵),故目前主要用于显式降采样。"""

    def compute(self, field):
        from scipy.interpolate import RegularGridInterpolator
        src = field.lattice
        dst = Lattice.from_preset(self.params["preset"])
        Xd, Yd, Zd = dst.mesh()
        pts = np.stack([Xd.ravel(), Yd.ravel(), Zd.ravel()], axis=-1)
        comps = []
        for c in range(3):
            interp = RegularGridInterpolator((src.xs, src.ys, src.zs),
                                             field.data[..., c])
            comps.append(interp(pts).reshape(dst.shape))
        return {"field": Field.vector(comps[0], comps[1], comps[2], dst)}
