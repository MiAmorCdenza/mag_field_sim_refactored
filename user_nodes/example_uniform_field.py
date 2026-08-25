"""示例用户插件:演示"丢一个 .py 文件即注册一个节点类型"。

本文件位于 user_nodes/(与 nodes/ 同权,同名 type 可覆盖内置)。
服务器热扫描本目录:文件放入后无需重启,节点面板自动出现。

示例节点:均匀矢量场(可调三分量),适合作为场叠加的基座。
"""
from __future__ import annotations

import numpy as np

from engine import register_node, Node, Param, Field


@register_node(
    type="uniform_field",
    name="均匀矢量场(用户插件示例)", category="用户/示例", icon="🧱",
    inputs={},
    outputs={"field": "vector_field"},
    params={
        "bx": Param("scalar", default=0.0),
        "by": Param("scalar", default=0.0),
        "bz": Param("scalar", default=1.0),
    },
    version=1,
)
class UniformFieldNode(Node):
    """全点阵恒定矢量场,演示用户自定义节点的完整形态。"""

    def compute(self):
        lat = self.lattice
        data = np.zeros((lat.nx, lat.ny, lat.nz, 3), dtype=np.float64)
        data[..., 0] = self.params["bx"]
        data[..., 1] = self.params["by"]
        data[..., 2] = self.params["bz"]
        return {"field": Field("vector", data, lat)}
