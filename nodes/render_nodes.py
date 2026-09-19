"""渲染域节点:声明式节点(不做数值求值),构成右栏渲染管线。

设计约定(渲染管线契约,2025 重构后):
- **不再有 prev/next 链**:渲染顺序由每个渲染项的 `layer` 参数决定
  (前端按 layer 分层挂载 + 设置 renderOrder)。历史纵向链是装饰性连接
  (前端按**节点类型**实例化渲染项,连线改不了绘制顺序),已移除(#28)
- 横向跨域边(场输出 → 渲染项.data)= 真数据契约:烘焙后对该场产出对应帧,
  通道名 = 渲染节点 id,由前端渲染项(JS 插件)执行渲染。
  实测:field_lines/efield_lines 的 data 是**必需**的;粒子/拖尾/预览三类
  的数据来自 WS 推送通道与客户端派生,data 仅作表达
- 渲染项实现三级来源:内置 items/*.js / user_render_items/*.js 文件插件
  (热扫)/ 节点 params["code"] 内联 JS 代码(图自包含,随图 JSON 持久化)

引擎行为:domain="render" 的节点不参与求值;_eval_node 防御性拒绝;
Graph.render_bindings() 产出绑定表供服务器编译数据通道。
"""
from __future__ import annotations

from engine import register_node, Node, Port, Param, GraphError

# 渲染项公共参数(颜色/可见性/透明度/层)
_RENDER_COMMON = {
    "visible": Param("bool", default=True),
    "color": Param("string", default="#88aaff"),
    "opacity": Param("scalar", default=0.9, min=0.0, max=1.0),
    # 场景层(0 静态场景/1 线/2 粒子/3 标记);同时作为 renderOrder
    "layer": Param("int", default=1, min=0, max=3,
                   desc="渲染层(0 静态/1 线/2 粒子/3 标记;越大越晚绘制)"),
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
    outputs={},
    params={
        # 全局渲染参数(宿主启动时应用一次;改参数即时生效)
        "background": Param("string", default="#0d1117", desc="视口背景色(hex)"),
        "fps_cap": Param("int", default=60, min=1, max=240,
                         desc="渲染循环上限(帧/秒)"),
    },
    version=1,
)
class RenderPipelineStartNode(RenderNodeBase):
    """渲染宿主入口:承载全局渲染参数(背景色 / 帧率上限)。

    不再有 next 链(顺序已由各渲染项的 layer 参数表达,#28)。
    """


@register_node(
    type="render_item_field_lines",
    name="磁力线渲染项", category="渲染", icon="🧲", domain="render",
    inputs={"data": Port("vector_field", default=None,
                         desc="场槽位(必需:#32 接线决定订阅,无数据边则不产出几何帧)")},
    outputs={},
    # 订阅通道(#32):data 端口的类型决定通道;未接线 = 不订阅(不渲染 + 告警)
    channels=["geometry:field_lines"],
    # 配套节点(#31):放置渲染项时补一个「渲染管线起始」(全局背景/帧率)
    companions=[{"type": "render_pipeline_start"}],
    params={
        **_RENDER_COMMON,
        # 留空 = 用渲染项自身的拓扑分类色(闭合蓝/开放红/太阳风绿);
        # 填值 = 所有线统一该色(覆盖分类色)
        "color": Param("string", default="",
                       desc="留空 = 用下方 color_mode;填值 = 全部线统一该色"),
        "color_mode": Param("enum", default="class",
                            choices=["class", "bmag", "reason", "solid"],
                            desc="class=拓扑分类(闭合蓝/开放红/太阳风绿);"
                                 "bmag=逐点场强(viridis+log,单位见右上角色标);"
                                 "reason=终止原因(落地/出域/绕圈/点数上限/场近零)"),
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
    inputs={"data": Port("vector_field", default=None,
                         desc="场槽位(必需:#32 接线决定订阅,无数据边则不产出几何帧)")},
    outputs={},
    channels=["geometry:efield_lines"],
    # 配套节点(#31):放置渲染项时补一个「渲染管线起始」(全局背景/帧率)
    companions=[{"type": "render_pipeline_start"}],
    params={
        **_RENDER_COMMON,
        "color": Param("string", default="",
                       desc="留空 = 用下方 color_mode;填值 = 全部线统一该色"),
        "color_mode": Param("enum", default="class",
                            choices=["class", "bmag", "reason", "solid"],
                            desc="class=默认暖黄;bmag=逐点场强(viridis+log);"
                                 "reason=终止原因(落地/出域/绕圈/点数上限/场近零)"),
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
    inputs={"data": Port("particle_buffer", default=None,
                         desc="粒子流(必需:接「输出编码器.particles」;"
                              "未接线 = 不渲染 + 告警)")},
    outputs={},
    channels=["particles"],
    # 配套节点(#31):放置渲染项时补一个「渲染管线起始」(全局背景/帧率)
    companions=[{"type": "render_pipeline_start"}],
    params={
        **_RENDER_COMMON,
        "layer": Param("int", default=2, min=0, max=3,
                       desc="渲染层(默认 2:粒子层)"),
        "size": Param("scalar", default=0.07, min=0.01, max=1.0),
    },
    version=1,
)
class RenderItemParticlesNode(RenderNodeBase):
    """粒子渲染:订阅粒子帧(21B/粒子二进制),数据从编码器的 particles 端口拉。"""


@register_node(
    type="render_item_particle_trails",
    name="粒子拖尾渲染项", category="渲染", icon="彡", domain="render",
    inputs={"data": Port("particle_buffer", default=None,
                         desc="粒子流(必需:接「输出编码器.particles」;"
                              "拖尾由客户端从该帧流派生)")},
    outputs={},
    channels=["particles"],
    # 配套节点(#31):放置渲染项时补一个「渲染管线起始」(全局背景/帧率)
    companions=[{"type": "render_pipeline_start"}],
    params={
        **_RENDER_COMMON,
        "layer": Param("int", default=2, min=0, max=3,
                       desc="渲染层(默认 2:粒子层)"),
        "trail_length": Param("int", default=30, min=0, max=200),
    },
    version=1,
)
class RenderItemParticleTrailsNode(RenderNodeBase):
    """粒子拖尾:客户端从已收粒子帧推导轨迹(零额外带宽)。

    trail_length = 每粒子轨迹点数(0 = 关闭);轨迹颜色随粒子物种。
    """

@register_node(
    type="render_item_particle_trace",
    name="粒子轨迹渲染项(累积)", category="渲染", icon="彡", domain="render",
    inputs={"data": Port("particle_buffer", default=None,
                         desc="粒子流(必需:接「输出编码器.particles」;"
                              "轨迹由客户端从该帧流累积)")},
    outputs={},
    channels=["particles"],
    # 配套节点(#31):放置渲染项时补一个「渲染管线起始」(全局背景/帧率)
    companions=[{"type": "render_pipeline_start"}],
    params={
        **_RENDER_COMMON,
        "layer": Param("int", default=2, min=0, max=3,
                       desc="渲染层(默认 2:粒子层)"),
        "max_points": Param("int", default=20000, min=100, max=200000,
                            desc="每粒子最多记录的点数;写满后**冻结但保留**轨迹"),
        "max_traced_particles": Param("int", default=8, min=1, max=64,
                                      desc="只对前 K 个粒子累积(控显存;其余不记录)"),
    },
    version=1,
)
class RenderItemParticleTraceNode(RenderNodeBase):
    """粒子轨迹(累积,不消失):与「粒子拖尾渲染项」并列的独立插件。

    区别:拖尾只保留最近 trail_length 个点(旧点被覆盖);
    本项一路累积,写满 max_points 后停止记录但**保留**轨迹 ——
    适合单粒子看完整轨道/漂移/弹跳。改参数重建不丢轨迹,重生才清。
    """


@register_node(
    type="render_item_source_preview",
    name="初条件预览渲染项", category="渲染", icon="◈", domain="render",
    inputs={"data": Port("source_spec", default=None,
                         desc="注入规格(必需:接「单粒子注入.spec」;"
                              "未接线 = 不显示预览)")},
    outputs={},
    channels=["source_preview"],
    # 配套节点(#31):放置渲染项时补一个「渲染管线起始」(全局背景/帧率)
    companions=[{"type": "render_pipeline_start"}],
    params={
        **_RENDER_COMMON,
        "layer": Param("int", default=3, min=0, max=3,
                       desc="渲染层(默认 3:标记层)"),
        "marker_size": Param("scalar", default=1.0, min=0.2, max=5.0),
    },
    version=1,
)
class RenderItemSourcePreviewNode(RenderNodeBase):
    """单粒子初条件预览:生成点 + 速度矢量(L1 本地计算,零带宽)。

    数据不来自烘焙帧:编辑器在参数变化时本地算出并直接派发
    "source_preview" 通道,故本节点无 data 输入。
    """


@register_node(
    type="render_item_diagnostics",
    name="诊断点渲染项", category="渲染", icon="✚", domain="render",
    inputs={"data": Port("scalar_field", default=None,
                         desc="标量场(待实现:当前无 JS 渲染项)")},
    outputs={},
    channels=["geometry:diagnostics"],
    # 配套节点(#31):放置渲染项时补一个「渲染管线起始」(全局背景/帧率)
    companions=[{"type": "render_pipeline_start"}],
    params={
        **_RENDER_COMMON,
        "marker_size": Param("scalar", default=0.3, min=0.05, max=2.0),
    },
    version=1,
)
class RenderItemDiagnosticsNode(RenderNodeBase):
    """诊断点渲染:标量场在诊断点处采样为标记点集。

    ⚠ 未实现:目前没有对应的 JS 渲染项文件,节点是占位(REFACTOR_PLAN #27)。
    """
