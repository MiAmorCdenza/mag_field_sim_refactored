"""来源类节点:Kp、日期(→倾角)、IMF(帕克螺旋)。"""
from __future__ import annotations

import math

import numpy as np

from engine import register_node, Node, Port, Param, Field


@register_node(
    type="kp_source",
    name="Kp 指数源", category="来源", icon="☀",
    inputs={},
    outputs={"kp": "scalar"},
    params={"kp": Param("scalar", default=2.0, min=0.0, max=9.0)},
)
class KpSourceNode(Node):
    """Kp 手动值。NOAA 自动拉取由服务器侧以 set_param 驱动(v1 保持 compute 纯函数)。"""

    def compute(self):
        return {"kp": self.params["kp"]}


@register_node(
    type="day_source",
    name="日期源", category="来源", icon="📅",
    inputs={},
    outputs={"ps": "scalar", "seasonal": "scalar", "total": "scalar"},
    params={"day": Param("scalar", default=172.0, min=0.0, max=365.0)},
)
class DaySourceNode(Node):
    """日期 → 偶极倾角,公式与旧 C++ 引擎 MagneticField.update_tilt 一致。"""

    def compute(self):
        day = self.params["day"]
        tilt_rot_max = math.radians(23.44)
        tilt_mag_offset = math.radians(11.0)
        seasonal = tilt_rot_max * math.cos(2.0 * math.pi * (day - 172.0) / 365.25)
        total = seasonal + tilt_mag_offset
        return {"ps": total, "seasonal": seasonal, "total": total}


@register_node(
    type="imf_source",
    name="IMF 帕克螺旋源", category="来源", icon="🌬",
    inputs={"kp": Port("scalar", default=2.0, min=0.0, max=9.0)},
    outputs={"field": "vector_field"},
    params={
        "polarity": Param("int", default=-1),   # -1=朝太阳(标准帕克), +1=背离
        "parker_custom": Param("bool", default=False),
        "parker_angle": Param("scalar", default=40.0, min=25.0, max=55.0),
    },
)
class ImfSourceNode(Node):
    """均匀 IMF 矢量场,忠实移植 legacy _build_parker_imf_components。

    未启用自定义角度时输出零场(与旧版行为一致)。
    """

    def compute(self, kp):
        lat = self.lattice
        pol_sign = -1 if self.params["polarity"] < 0 else 1
        if not self.params["parker_custom"]:
            bx = by = bz = 0.0
        else:
            theta = np.radians(self.params["parker_angle"])
            b_ref = 3.0 + kp * 0.5
            b_total = b_ref * np.sqrt(2.0)  # 保持 45° 时模长一致
            bx = pol_sign * b_total * np.cos(theta)
            by = -pol_sign * b_total * np.sin(theta)
            bz = 0.0
        data = np.zeros((lat.nx, lat.ny, lat.nz, 3), dtype=np.float64)
        data[..., 0] = bx
        data[..., 1] = by
        data[..., 2] = bz
        return {"field": Field("vector", data, lat)}
