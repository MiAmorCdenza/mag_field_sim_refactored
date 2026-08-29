"""粒子域节点:C++ 实时管线的声明桩(编辑期编译为执行计划,L1)。

设计约定(REFACTOR_PLAN §5.7,与渲染域同模式):
- domain="particle" 的节点不在 Python 求值 —— 引擎只负责:
  1) 图校验(端口类型/拓扑,load_json)
  2) particle_plan():编译为执行计划 JSON,由 C++ 原生管线执行
    (全原生 = 每帧零 Python,slow_path 标志保留给未来 Python 算子)
- 链边(prev/next,any)= 粒子管线顺序(发射器 → 积分器 → 编码器),
  视觉上粒子域在中列垂直链,与渲染域右链同约定
- 数据边(b/e/drag)= 场槽位绑定:上游 output_slot 的 slot 参数,
  或 outputs 中声明的槽位名;未连接 = null(可选场)
- 每内核一个节点类型:换步进器 = 图上换节点(L1 决策;内核实现在
  server/core/advancers.h 注册,未来 L2 DLL SDK 以同接口外置)
- 参数 schema 与 C++ 侧原生节点镜像(节点编辑器中同一套参数 UI)
"""
from __future__ import annotations

from engine import register_node, Node, Port, Param, GraphError


class ParticleNodeBase(Node):
    """粒子域节点基类:声明性,任何 Python 求值尝试都报错。"""

    def compute(self, **inputs):
        raise GraphError(
            f"粒子域节点 {self.spec().get('type')} 由 C++ 原生管线执行,"
            f"不参与 Python 求值")


_EMITTER_PARAMS = {
    "mode": Param("int", default=0, min=0, max=2),
    "lon": Param("scalar", default=0.0, min=-180.0, max=180.0),
    "lat": Param("scalar", default=0.0, min=-90.0, max=90.0),
    "v_base": Param("scalar", default=400.0, min=50.0, max=2000.0),
    "v_random": Param("scalar", default=10.0, min=0.0, max=100.0),
    "angle_random": Param("scalar", default=5.0, min=0.0, max=100.0),
    "dist_ratio": Param("scalar", default=1.0, min=0.01, max=5.0),
    "spawn_radius_ratio": Param("scalar", default=0.5, min=0.01, max=5.0),
    "max_range": Param("scalar", default=90.0, min=5.0, max=200.0),
}

# 积分器公共输入(prev=链序边;b/e/drag=场槽位数据边)
_INTEGRATOR_INPUTS = {
    "prev": Port("any", default=None),
    "b": Port("vector_field", default=None),
    "e": Port("vector_field", default=None),
    "drag": Port("scalar_field", default=None),
}

_INTEGRATOR_PARAMS = {
    "dt": Param("scalar", default=0.01, min=0.0001, max=1.0),
    "substeps": Param("int", default=5, min=1, max=50),
    "max_range": Param("scalar", default=90.0, min=5.0, max=200.0),
    "enable_gravity": Param("bool", default=False),
    "gravity_mult": Param("scalar", default=1.0, min=0.0, max=10.0),
    "substep_cap": Param("int", default=20, min=1, max=200),
}

# 物种预设(归一化单位:电荷 = 元电荷 e,质量 = 质子质量)。
# 参照老版本可编辑元素:name / q / m / v_mult / weight / color / checked,
# 但以"一个节点 = 一个物种"重新组织(checked → enabled 参数)。
_SPECIES_PRESETS = {
    "electron": {"name": "电子", "q": -1.0, "mass": 1.0 / 1836.0,
                 "v_mult": 1.0, "weight": 1.0, "color": "#5599ff"},
    "proton": {"name": "质子", "q": 1.0, "mass": 1.0,
               "v_mult": 1.0, "weight": 1.0, "color": "#ff5555"},
    "alpha": {"name": "α粒子", "q": 2.0, "mass": 4.0,
              "v_mult": 1.0, "weight": 1.0, "color": "#ffaa33"},
}


@register_node(
    type="particle_emitter",
    name="粒子发射器", category="粒子/来源", icon="⏺", domain="particle",
    inputs={},
    outputs={"next": "any"},
    params=_EMITTER_PARAMS,
    version=1,
)
class ParticleEmitterNode(ParticleNodeBase):
    """粒子发射器:参数镜像 C++ EmitterConfig。

    类型列表来自图中声明式 particle_species 节点(计划编译时聚合);
    无物种节点时沿用服务器默认三种类型。
    """


@register_node(
    type="particle_species",
    name="粒子物种", category="粒子/来源", icon="◉", domain="particle",
    inputs={},
    outputs={"out": "any"},
    params={
        "preset": Param("enum", default="custom",
                        choices=["custom", "electron", "proton", "alpha"],
                        desc="预设:选择后自动填充下方字段(再编辑即转自定义)"),
        "name": Param("string", default="自定义粒子", desc="显示名称"),
        "q": Param("scalar", default=1.0, desc="电荷(单位:元电荷 e)"),
        "mass": Param("scalar", default=1.0, desc="质量(质子=1)"),
        "v_mult": Param("scalar", default=1.0, min=0.0, max=10.0,
                        desc="速度倍率"),
        "weight": Param("scalar", default=1.0, min=0.0, max=100.0,
                        desc="生成权重(按权重随机抽取)"),
        "color": Param("string", default="#ff5555", desc="渲染颜色(hex)"),
        "enabled": Param("bool", default=True, desc="参与生成(对应老版 checked)"),
    },
    presets=_SPECIES_PRESETS,
    version=1,
)
class ParticleSpeciesNode(ParticleNodeBase):
    """粒子物种声明:一个节点 = 一个物种,计划编译时聚合进发射器。

    元素参照老版本 particle_types 的 name/q/m/v_mult/weight/color/checked;
    设计上不用"发射器内的列表",而是独立声明节点 —— 物种可插拔、
    可组合(与场的原子节点同一哲学)。
    """

    def __init__(self, node_id, params=None):
        super().__init__(node_id, params)
        # 加载时即按预设填充(JSON 里只有 {"preset": "electron"} 也能
        # 得到完整的 q/mass/v_mult/color/name)
        p = self.params.get("preset")
        if p in _SPECIES_PRESETS:
            for k, v in _SPECIES_PRESETS[p].items():
                self.params.setdefault(k, v)

    def on_param(self, name, old, new):
        # 预设 → 自动填充;手动改物理量 → 转为自定义
        if name == "preset" and new in _SPECIES_PRESETS:
            for k, v in _SPECIES_PRESETS[new].items():
                self.params[k] = v
        elif name in ("name", "q", "mass", "v_mult", "weight", "color"):
            self.params["preset"] = "custom"


@register_node(
    type="boris_integrator",
    name="Boris 积分器", category="粒子/积分", icon="⑂", domain="particle",
    inputs=_INTEGRATOR_INPUTS,
    outputs={"next": "any"},
    params=_INTEGRATOR_PARAMS,
    version=1,
)
class BorisIntegratorNode(ParticleNodeBase):
    """相对论 Boris(legacy 内核,默认图位级一致基准)。"""


@register_node(
    type="leapfrog_integrator",
    name="蛙跳积分器", category="粒子/积分", icon="⑃", domain="particle",
    inputs=_INTEGRATOR_INPUTS,
    outputs={"next": "any"},
    params=_INTEGRATOR_PARAMS,
    version=1,
)
class LeapfrogIntegratorNode(ParticleNodeBase):
    """蛙跳:Boris 旋转(磁)+ 踢-漂-踢(E/引力/阻力),|v| 保模。"""


@register_node(
    type="rk4_integrator",
    name="RK4 积分器", category="粒子/积分", icon="⑄", domain="particle",
    inputs=_INTEGRATOR_INPUTS,
    outputs={"next": "any"},
    params=_INTEGRATOR_PARAMS,
    version=1,
)
class Rk4IntegratorNode(ParticleNodeBase):
    """经典 4 阶 Runge-Kutta(每步 4 次场采样)。"""


@register_node(
    type="verlet_integrator",
    name="速度 Verlet 积分器", category="粒子/积分", icon="⑅", domain="particle",
    inputs=_INTEGRATOR_INPUTS,
    outputs={"next": "any"},
    params=_INTEGRATOR_PARAMS,
    version=1,
)
class VerletIntegratorNode(ParticleNodeBase):
    """速度 Verlet:Boris 旋转(磁)+ 位置先行(E/引力),|v| 保模。"""


@register_node(
    type="output_encoder",
    name="输出编码器", category="粒子/输出", icon="⇥", domain="particle",
    inputs={"prev": Port("any", default=None)},
    outputs={},
    params={},
    version=1,
)
class OutputEncoderNode(ParticleNodeBase):
    """粒子帧编码(21 字节/粒子二进制协议,v1 无参数)。"""
