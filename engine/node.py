"""节点基类。

约定(REFACTOR_PLAN §5.2):
- compute(**inputs) 是纯函数:输入(Field / 标量)→ 输出 dict
- 不自己碰缓存、不碰图状态;spec 由 @register_node 装饰器注入
- 节点实例可通过 self.graph 访问所在图(取点阵等)
"""
from __future__ import annotations


class Node:
    def __init__(self, node_id, params=None):
        self.node_id = node_id
        self.params = dict(params or {})          # params 类参数
        self.input_defaults = {}                   # 输入端口参数覆盖(滑块值)
        self.graph = None                          # 由 Graph.add_node 注入

    # ---- 元信息 ----
    @classmethod
    def spec(cls):
        """@register_node 注入的元信息 dict。

        keys: type/name/category/domain/impl/cost/lattice/icon/version
              inputs {名: Port} / outputs {名: 类型} / params {名: Param}
        """
        return cls._node_spec

    @property
    def lattice(self):
        """所在图的点阵(v1 图级单点阵)。"""
        return self.graph.lattice if self.graph else None

    # ---- 插件实现点 ----
    def compute(self, **inputs):
        """核心实现:inputs -> {output_name: value}。

        value 可为 Field / np.ndarray / 标量;图负责包装与赋 id。
        """
        raise NotImplementedError

    def validate(self):
        """静态检查,返回警告字符串列表。"""
        return []

    def on_param(self, name, old, new):
        """参数变化钩子(原生节点转发到 C++ setter 用)。"""
        pass

    def __repr__(self):
        return f"<{self.spec().get('type')} '{self.node_id}'>"
