"""输出节点:把"最终渲染环节"显式化为终端节点(Nuke/Blender 式 OutputNode)。

用法:从面板添加「输出槽」节点 → 把场连线到其 field 输入 → 把 slot 参数
改成槽位名(如 B / E / drag)。引擎加载图时自动把每个 output_slot 实例
推导为同名命名输出(C++ 按名订阅),无需再手写 outputs JSON。
"""
from __future__ import annotations

from engine import register_node, Node, Port, Param


@register_node(
    type="output_slot",
    name="输出槽(最终节点)", category="输出", icon="📤",
    role="output",  # 引擎据此自动推导命名输出
    inputs={"field": Port("any", default=None)},
    outputs={"out": "any"},
    params={"slot": Param("string", default="B")},
    version=1,
)
class OutputSlotNode(Node):
    """场链终端:输入透传为命名输出槽。"""

    def compute(self, field):
        return {"out": field}
