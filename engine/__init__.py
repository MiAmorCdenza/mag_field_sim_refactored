"""EarthMagFieldSim 动态节点引擎(控制面)。

按 REFACTOR_PLAN.md 实现:
- 场域节点图:拉取式求值 + 节点级内容寻址缓存(烘焙期,秒级)
- 插件注册表:一个 .py = 一个节点类型,动态加载
- 输出槽位自由声明(图 JSON 的 outputs),C++ 按名订阅

纯 Python,仅依赖 numpy(重采样节点额外依赖 scipy)。
粒子域(原生算子与执行计划)在后续阶段接入。
"""
from .lattice import Lattice, stretched_axis, AXIS_PRESETS, LATTICE_PRESETS
from .field import Field
from .ports import Port, Param, PORT_TYPES, SCALAR_TYPES, FIELD_TYPES, coerce_scalar
from .node import Node
from .registry import register_node, Registry, default_registry
from .graph import Graph, GraphError

__version__ = "0.1.0"
__all__ = [
    "Lattice", "stretched_axis", "AXIS_PRESETS", "LATTICE_PRESETS",
    "Field", "Port", "Param", "PORT_TYPES", "SCALAR_TYPES", "FIELD_TYPES",
    "coerce_scalar", "Node", "register_node", "Registry", "default_registry",
    "Graph", "GraphError",
]
