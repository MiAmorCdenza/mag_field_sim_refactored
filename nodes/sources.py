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


@register_node(
    type="tilt_source",
    # #54 界面注记:docstring 自动成为「说明」,formula 由内置 KaTeX 渲染
    formula=r"\psi=\arcsin\!\big(\sin 23.44^\circ\cdot\cos H\big)",
    name="倾角源(日期→倾角)", category="来源", icon="📐",
    inputs={},
    outputs={"ps": "scalar", "bd": "scalar"},
    params={
        "year": Param("int", default=2026, min=1901, max=2099,
                      desc="日期 → 倾角(与 IGRF 偶极强度)"),
        "month": Param("int", default=6, min=1, max=12),
        "day": Param("int", default=21, min=1, max=31),
        "ut": Param("scalar", default=12.0, min=0.0, max=24.0,
                    desc="UT 小时(含小数):倾角有周日变化"),
    },
    version=1,
)
class TiltSourceNode(Node):
    """日期/UT → **偶极倾角 ps(度)** 与赤道偶极场 B0(nT)。

    直接调用 A2000 模型自己的 `TRANS/IDD`(models/a2000.dll),因此与
    `A2000 抛物面(内场)` 内部用的倾角**完全一致**(实测 Δψ = 0);同一个倾角源
    可以同时喂 偶极子 / T89 / A2000 → 三者倾角严格相同,对照才有意义。

    物理:倾角季节变化 ±23.4°(二至点最大、二分点≈0),另有周日摆动
    (偶极轴相对日地线的投影);B0 随年份缓慢减小(IGRF 长期变化 ≈ −18 nT/年)。
    """

    def compute(self):
        try:
            from nodes._a2000_dll import _load_lib, _StdoutSilencer
        except ImportError:
            from _a2000_dll import _load_lib, _StdoutSilencer
        lib = _load_lib()
        if lib is None:
            raise GraphError("倾角源需要 models/a2000.dll:先运行 "
                             "scripts\\build_a2000.ps1(与 A2000 节点同源,"
                             "保证倾角换算与模型内部逐位一致)")
        import ctypes
        psi = ctypes.c_double(0.0)
        bd = ctypes.c_double(0.0)
        with _StdoutSilencer():
            lib.a2000_tilt(float(self.params["ut"]), int(self.params["year"]),
                           int(self.params["month"]), int(self.params["day"]),
                           ctypes.byref(psi), ctypes.byref(bd))
        # ⚠ 符号约定:A2000 的 par(1) 与 geopack/T89/本项目 ps **相反**(实测:
        # 夏至时模型内部 ψ=−25.8°,而它给出的场等效于我们的 ps=+25.8°,
        # 判据 = 赤道侧面 (0,2,0) 的 B_x 符号)。这里取负,统一成
        # "北轴朝日为正式"的标准约定,避免一个倾角源喂出两种朝向。
        return {"ps": -float(psi.value), "bd": float(bd.value)}