"""渲染项插件示例:俯仰角锥(#32 动态渲染插件契约的最小完整示例)。

这个文件演示"**丢文件即新节点**"的两半之一(Python 声明侧),另一半是同名
JS 渲染项 `static/renderer/items/pitch_cone.js`。放好两个文件后:
  1. registry 热扫 → 调色板出现「俯仰角锥渲染项」,无需重启服务器
  2. 拖入画布 → 把「单粒子注入」的 spec 接到它的 data 输入(接线决定订阅)
  3. 服务器广播 source_preview 时,锥体随参数实时更新

契约(照抄即可写新插件):
  - `domain="render"` + 声明 `inputs={"data": Port("<被消费的端口类型>")}`
  - `channels=[...]` = 消费的数据通道(与生产者输出端口类型对应):
      field_table 类(vector_field/scalar_field) → "geometry:<kind>"
      particle_buffer                            → "particles"
      source_spec                                → "source_preview"
  - 数据端口**未接线 = 不订阅**(不渲染,并由服务器告警)
  - JS 侧实现 setup/onData/onParam/dispose(见 items/pitch_cone.js)
"""
from __future__ import annotations

from engine import register_node, Node, Port, Param, GraphError

_RENDER_COMMON = {
    "visible": Param("bool", default=True),
    "color": Param("string", default="#ffcc66"),
    "opacity": Param("scalar", default=0.35, min=0.0, max=1.0),
    "layer": Param("int", default=3, min=0, max=3,
                   desc="渲染层(默认 3:标记层)"),
    "code": Param("string", default=""),   # 内联 JS 实现(空 = 用文件插件)
}


@register_node(
    type="render_item_pitch_cone",
    name="俯仰角锥渲染项", category="渲染", icon="⌒", domain="render",
    inputs={"data": Port("source_spec", default=None,
                         desc="注入规格(接「单粒子注入.spec」;"
                              "未接线 = 不显示)")},
    outputs={},
    channels=["source_preview"],   # 消费单粒子初条件预览通道
    companions=[{"type": "render_pipeline_start"}],
    params={
        **_RENDER_COMMON,
        "radius": Param("scalar", default=1.6, min=0.1, max=8.0,
                        desc="锥体长度(Re,视觉尺度)"),
        "rings": Param("int", default=3, min=1, max=8,
                       desc="同轴参考环数量(画成漏斗状,便于看角度)"),
    },
    version=1,
)
class RenderItemPitchConeNode(Node):
    """俯仰角锥:以局部 B̂ 为轴、俯仰角为半顶角画一个锥(可视化 v 与 B 的夹角)。

    数据来自服务器的 source_preview(含局部 B 与俯仰角),因此锥体是**物理
    一致**的:拖 pitch 滑杆 → 服务器预览更新 → 锥体随即张开/收拢。
    """

    def compute(self, **inputs):
        raise GraphError(
            "渲染域节点 render_item_pitch_cone 是声明节点,不参与数值求值")
