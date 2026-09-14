"""单粒子注入插件:确定性初条件(零随机),连接后发射器切单粒子模式。

插件形态(与 particle_species 同构,详见 REFACTOR_PLAN §5.7):
- 独立文件,registry 扫描即注册(丢弃/修改即热加载)
- 声明式节点:domain="particle" 不参与 Python 求值,plan 编译为
  `injection` 算子 → C++ InjectionConfig → Emitter mode 3
- 端口化组合:spec 输出 → 发射器 init 输入(连上即生效)
- 物理约定:
  * 位置 (r, lat, lon) 为 GSM 球坐标(Re / 度);或直接 (x, y, z)
  * 速度 vpitch 模式:俯仰角相对**局部磁力线方向 B̂**,
    v = v·(cosα·B̂ + sinα·(cosφ·ê₁ + sinφ·ê₂)),φ = 回旋相位
    α=90° 垂直于 B(磁镜捕获), α=0° 沿 B(束流)
  * 速度 vxyz 模式:直接给定三分量(km/s),不需磁场
- 粒子种类(电荷/质量/颜色)由 particle_species 链提供,取链首启用项
"""
from __future__ import annotations

from engine import register_node, Node, Port, Param, GraphError


@register_node(
    type="particle_injection",
    name="单粒子注入", category="粒子/来源", icon="◈", domain="particle",
    inputs={},
    outputs={"spec": "any"},
    params={
        # ---- 位置 ----
        "pos_mode": Param("enum", default="rll", choices=["rll", "xyz"],
                          desc="位置表示:rll=地心距+纬度+经度 / xyz=直接坐标"),
        "r": Param("scalar", default=6.6, desc="地心距(Re)"),
        "lat": Param("scalar", default=0.0, min=-90.0, max=90.0,
                     desc="纬度(度,GSM)"),
        "lon": Param("scalar", default=0.0, min=-180.0, max=180.0,
                     desc="经度(度,GSM)"),
        "x": Param("scalar", default=6.6, desc="x(Re,GSM)"),
        "y": Param("scalar", default=0.0, desc="y(Re,GSM)"),
        "z": Param("scalar", default=0.0, desc="z(Re,GSM)"),
        # ---- 速度 ----
        "vel_mode": Param("enum", default="vpitch", choices=["vpitch", "vxyz"],
                          desc="速度表示:vpitch=速率+俯仰角+回旋相位(相对局部B)"
                               " / vxyz=三分量"),
        "v": Param("scalar", default=400.0, desc="速率(km/s)"),
        "pitch": Param("scalar", default=90.0, min=0.0, max=180.0,
                       desc="俯仰角(度,相对局部磁力线;90=磁镜捕获)"),
        "phase": Param("scalar", default=0.0, min=-180.0, max=180.0,
                       desc="回旋相位(度)"),
        "vx": Param("scalar", default=0.0, desc="vx(km/s)"),
        "vy": Param("scalar", default=0.0, desc="vy(km/s)"),
        "vz": Param("scalar", default=400.0, desc="vz(km/s)"),
    },
    version=1,
)
class ParticleInjectionNode(Node):
    """单粒子注入:确定性初条件;接发射器 init 端口即生效。"""

    def compute(self, **inputs):
        raise GraphError(
            "粒子域节点 particle_injection 由 C++ 原生管线执行,"
            "不参与 Python 求值")
