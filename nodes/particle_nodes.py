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


@register_node(
    type="particle_emitter",
    name="粒子发射器", category="粒子/来源", icon="⏺", domain="particle",
    inputs={},
    outputs={"next": "any"},
    params=_EMITTER_PARAMS,
    version=1,
)
class ParticleEmitterNode(ParticleNodeBase):
    """粒子发射器:参数镜像 C++ EmitterConfig(粒子类型列表 v1 走服务器默认)。"""


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
