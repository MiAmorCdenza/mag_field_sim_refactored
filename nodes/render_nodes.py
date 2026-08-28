"""渲染域节点:声明式节点(不做数值求值),构成右栏渲染管线。

设计约定(渲染管线契约):
- 纵向链边(prev/next,any 类型)= 管线成员关系与视觉顺序(语义上顺序无关)
- 横向跨域边(场输出 → 渲染项.data)= 数据契约:烘焙后对该场产出对应帧,
  通道名 = 渲染节点 id,由前端渲染项(JS 插件)执行渲染
- 渲染项实现三级来源:内置 items/*.js / user_render_items/*.js 文件插件
  (热扫)/ 节点 params["code"] 内联 JS 代码(图自包含,随图 JSON 持久化)

引擎行为:domain="render" 的节点不参与求值;_eval_node 防御性拒绝;
Graph.render_bindings() 产出绑定表供服务器编译数据通道。
"""
from __future__ import annotations

from engine import register_node, Node, Port, Param, GraphError

# 渲染项公共参数(颜色/可见性/透明度)
_RENDER_COMMON = {
    "visible": Param("bool", default=True),
    "color": Param("string", default="#88aaff"),
    "opacity": Param("scalar", default=0.9, min=0.0, max=1.0),
    "code": Param("string", default=""),  # 内联 JS 实现(空 = 用文件插件)
}


class RenderNodeBase(Node):
    """渲染域节点基类:声明性,任何求值尝试都报错。"""

    def compute(self, **inputs):
        raise GraphError(
            f"渲染域节点 {self.spec().get('type')} 是声明节点,不参与数值求值")


@register_node(
    type="render_pipeline_start",
    name="渲染管线起始", category="渲染", icon="◆", domain="render",
    inputs={},
    outputs={"next": "any"},
    params={
        "background": Param("string", default="#0d1117"),
        "fps_cap": Param("int", default=60, min=1, max=240),
    },
    version=1,
)
class RenderPipelineStartNode(RenderNodeBase):
    """渲染宿主入口:垂直链的顶端,携带全局渲染参数。"""


@register_node(
    type="render_item_field_lines",
    name="磁力线渲染项", category="渲染", icon="🧲", domain="render",
    inputs={"prev": Port("any", default=None),
            "data": Port("vector_field", default=None)},
    outputs={},
    params={
        **_RENDER_COMMON,
        "dsmax": Param("scalar", default=0.2, min=0.05, max=2.0),
        "err": Param("scalar", default=1e-4, min=1e-6, max=1e-2),
        "arrows": Param("bool", default=True),
        "arrow_spacing": Param("scalar", default=2.5, min=0.5, max=20.0),
    },
    version=1,
)
class RenderItemFieldLinesNode(RenderNodeBase):
    """场线追踪渲染:B 场表 → TRACE_08 几何 → 前端渲染。"""


@register_node(
    type="render_item_efield_lines",
    name="电场线渲染项", category="渲染", icon="⚡", domain="render",
    inputs={"prev": Port("any", default=None),
            "data": Port("vector_field", default=None)},
    outputs={},
    params={
        **_RENDER_COMMON,
        "dsmax": Param("scalar", default=0.2, min=0.05, max=2.0),
        "err": Param("scalar", default=1e-4, min=1e-6, max=1e-2),
        "arrows": Param("bool", default=True),
        "arrow_spacing": Param("scalar", default=3.0, min=0.5, max=20.0),
    },
    version=1,
)
class RenderItemEFieldLinesNode(RenderNodeBase):
    """电场线追踪渲染:E 场表 → 几何 → 前端渲染。"""


@register_node(
    type="render_item_particles",
    name="粒子渲染项", category="渲染", icon="●", domain="render",
    inputs={"prev": Port("any", default=None),
            "data": Port("particle_buffer", default=None)},
    outputs={},
    params={
        **_RENDER_COMMON,
        "size": Param("scalar", default=0.07, min=0.01, max=1.0),
    },
    version=1,
)
class RenderItemParticlesNode(RenderNodeBase):
    """粒子渲染:订阅粒子帧(21B/粒子二进制)。"""


@register_node(
    type="render_item_diagnostics",
    name="诊断点渲染项", category="渲染", icon="✚", domain="render",
    inputs={"prev": Port("any", default=None),
            "data": Port("scalar_field", default=None)},
    outputs={},
    params={
        **_RENDER_COMMON,
        "marker_size": Param("scalar", default=0.3, min=0.05, max=2.0),
    },
    version=1,
)
class RenderItemDiagnosticsNode(RenderNodeBase):
    """诊断点渲染:标量场在诊断点处采样为标记点集。"""
