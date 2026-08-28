"""引擎冒烟测试:验证 Lattice/Field/Registry/Graph 核心路径。

运行: python tests/test_engine_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from engine import (Lattice, Field, Port, Param, Node, register_node,
                    Registry, Graph, GraphError)


# ---------- 用程序化注册定义测试节点(不走插件文件) ----------
@register_node(
    type="test_const",
    inputs={},
    outputs={"value": "scalar"},
    params={"value": Param("scalar", default=2.0)},
)
class ConstNode(Node):
    def compute(self):
        return {"value": self.params["value"]}


@register_node(
    type="test_fill",
    inputs={"value": Port("scalar_field")},
    outputs={"field": "scalar_field"},
)
class FillNode(Node):
    """接收端口声明为 scalar_field:引擎把标量源广播为场后传入。"""

    def compute(self, value):
        # 引擎已将 scalar 广播为 scalar_field
        assert isinstance(value, Field) and value.kind == "scalar"
        return {"field": value.data * 2.0}


@register_node(
    type="test_add",
    inputs={"a": Port("scalar_field"), "b": Port("scalar_field")},
    outputs={"sum": "scalar_field"},
)
class AddNode(Node):
    def compute(self, a, b):
        return {"sum": a.data + b.data}


@register_node(
    type="test_field_passthrough",
    inputs={},
    outputs={"field": "vector_field"},
)
class FieldPassthroughNode(Node):
    """回归:节点直接返回 Field(真实场节点形态)——引擎必须赋新 id。"""

    def compute(self):
        lat = self.lattice
        data = np.zeros((lat.nx, lat.ny, lat.nz, 3), dtype=np.float64)
        return {"field": Field("vector", data, lat)}  # 无 id


def test_field_id_assigned():
    """节点返回裸 Field 时,引擎应克隆并赋新 id(否则缓存永不失效)。"""
    g = make_graph()
    g.add_node("raw", "test_field_passthrough")
    g.declare_output("R", "raw", "field")
    id1 = g.evaluate(["R"])["R"].id
    assert id1 is not None, "Field id 必须由引擎分配"
    id2 = g.evaluate(["R"])["R"].id
    assert id2 == id1, "缓存命中返回同一 id"
    print("✓ 节点返回 Field 时 id 由引擎分配")


@register_node(
    type="test_output_slot",
    role="output",  # 角色标记:引擎据此自动推导输出槽
    inputs={"field": Port("any", default=None)},
    outputs={"out": "any"},
    params={"slot": Param("string", default="B")},
)
class TestOutputSlotNode(Node):
    """透传输出节点(与 nodes/outputs.py 同构)。"""

    def compute(self, field):
        return {"out": field}


def test_output_slot_auto_declare():
    """output_slot 节点在 load_json 时自动推导为命名输出槽。"""
    g = make_graph()
    g.add_node("os", "test_output_slot", {"slot": "B2"})
    g.connect("add", "sum", "os", "field")
    doc = g.to_json()
    g2 = Graph(g.registry, None)
    g2.load_json(doc)
    assert "B2" in g2.outputs, "output_slot 应自动声明输出槽"
    assert g2.outputs["B2"] == ("os", "out")
    baked = g2.bake(["B2"])
    assert np.allclose(np.asarray(baked["B2"]["scalar"]), 16.0)
    print("✓ output_slot 节点自动推导输出槽")


def test_auto_layout():
    """缺位置的图在 load_json 时自动做层次化排布。"""
    g = make_graph()  # add_node 未传 pos → _pos 为空
    doc = g.to_json()
    g2 = Graph(g.registry, None)
    g2.load_json(doc)
    assert all(nid in g2._pos for nid in g2.nodes), "所有节点应有位置"
    xs = sorted({g2._pos[n][0] for n in g2.nodes})
    assert len(xs) >= 3, "应形成多个层次列"
    # 源节点在左,汇节点在右
    assert g2._pos["c1"][0] < g2._pos["f1"][0] < g2._pos["add"][0]
    print("✓ 层次化自动排布(源左→汇右)")


@register_node(
    type="test_render_start",
    domain="render",
    inputs={},
    outputs={"next": "any"},
    params={},
)
class TestRenderStart(Node):
    def compute(self, **inputs):
        raise GraphError("渲染域节点不应被求值")


@register_node(
    type="test_render_item",
    domain="render",
    inputs={"prev": Port("any", default=None),
            "data": Port("scalar_field", default=None)},
    outputs={},
    params={"color": Param("string", default="#ffffff")},
)
class TestRenderItem(Node):
    def compute(self, **inputs):
        raise GraphError("渲染域节点不应被求值")


def test_render_domain():
    """渲染域:声明节点不求值、绑定表正确、排布在最右列。"""
    g = make_graph()
    g.add_node("rp", "test_render_start")
    g.add_node("ri", "test_render_item", {"color": "#ff0000"})
    g.connect("rp", "next", "ri", "prev")              # 垂直链(成员关系)
    g.connect("add", "sum", "ri", "data")              # 跨域数据契约

    # 绑定表
    binds = {b["node_id"]: b for b in g.render_bindings()}
    assert set(binds) == {"rp", "ri"}
    assert binds["ri"]["inputs"]["data"] == ["add", "sum"]
    assert binds["ri"]["params"]["color"] == "#ff0000"
    assert binds["ri"]["type"] == "test_render_item"

    # 场输出烘焙不受渲染域影响
    assert np.allclose(g.bake(["S"])["S"]["scalar"], 16.0)

    # 渲染域节点防御性拒绝求值
    try:
        g._eval_node("ri")
        raise AssertionError("渲染域节点不应可求值")
    except GraphError as e:
        assert "渲染域" in str(e)

    # JSON 往返后绑定保留
    g2 = Graph(g.registry, None)
    g2.load_json(g.to_json())
    binds2 = {b["node_id"]: b for b in g2.render_bindings()}
    assert binds2["ri"]["inputs"]["data"] == ["add", "sum"]

    # 排布:渲染域在最右列
    g2.auto_layout()
    assert g2._pos["rp"][0] > g2._pos["add"][0]
    assert g2._pos["ri"][0] > g2._pos["add"][0]
    assert g2._pos["rp"][1] < g2._pos["ri"][1]  # 起始在链顶
    print("✓ 渲染域声明节点:绑定表/防御求值/JSON往返/右列垂直链")


def make_graph():
    reg = Registry([])  # 空插件目录,类型已在上面程序化注册
    reg.scan()          # scan 会吸收 _REGISTERED 中的程序化注册
    lat = Lattice(np.linspace(-2, 2, 5), np.linspace(-1, 1, 3),
                  np.linspace(0, 1, 2), name="tiny")
    g = Graph(reg, lat)
    g.add_node("c1", "test_const", {"value": 3.0})
    g.add_node("c2", "test_const", {"value": 5.0})
    g.add_node("f1", "test_fill")
    g.add_node("f2", "test_fill")
    g.add_node("add", "test_add")
    g.connect("c1", "value", "f1", "value")
    g.connect("c2", "value", "f2", "value")
    g.connect("f1", "field", "add", "a")
    g.connect("f2", "field", "add", "b")
    g.declare_output("S", "add", "sum")
    return g


def test_evaluate():
    g = make_graph()
    out = g.evaluate(["S"])["S"]
    # 3*2 + 5*2 = 16 全网格
    assert out.kind == "scalar"
    assert np.allclose(out.data, 16.0), out.data
    print("✓ 求值与广播正确")


def test_cache_invalidation():
    g = make_graph()
    id1 = g.evaluate(["S"])["S"].id
    id2 = g.evaluate(["S"])["S"].id
    assert id1 == id2, "命中缓存应返回同一 Field id"
    g.set_param("c1", "value", 4.0)   # 改参数 → c1/f1/add 键变化 → 重算
    out = g.evaluate(["S"])["S"]
    assert out.id != id1, "参数变化后应重算(新 id)"
    assert np.allclose(out.data, 18.0), out.data  # 4*2 + 5*2
    print("✓ 内容寻址缓存与失效正确")


def test_json_roundtrip():
    g = make_graph()
    doc = g.to_json()
    g2 = Graph(g.registry, None)
    g2.load_json(doc)
    assert np.allclose(g2.evaluate(["S"])["S"].data, 16.0)
    print("✓ JSON 往返一致")


def test_cycle_rejected():
    g = make_graph()
    try:
        g.connect("add", "sum", "c1", "value")  # 标量场→标量 不允许(类型错)
        raise AssertionError("应拒绝类型不兼容")
    except GraphError as e:
        print(f"✓ 类型校验拒绝: {e}")


def test_unknown_type_rejected():
    g = make_graph()
    try:
        g.add_node("x", "no_such_type")
        raise AssertionError("应拒绝未知类型")
    except GraphError as e:
        print(f"✓ 未知类型拒绝: {e}")


def test_bake_format():
    g = make_graph()
    baked = g.bake(["S"])
    assert set(baked["S"]) == {"xs", "ys", "zs", "scalar"}
    assert len(baked["S"]["scalar"]) == 5 * 3 * 2
    print("✓ bake 传输格式正确")


if __name__ == "__main__":
    test_evaluate()
    test_cache_invalidation()
    test_json_roundtrip()
    test_cycle_rejected()
    test_unknown_type_rejected()
    test_bake_format()
    test_field_id_assigned()
    test_output_slot_auto_declare()
    test_auto_layout()
    test_render_domain()
    print("\n全部冒烟测试通过 ✅")
