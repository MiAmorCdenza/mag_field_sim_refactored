"""引擎冒烟测试:验证 Lattice/Field/Registry/Graph 核心路径。

运行: python tests/test_engine_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from engine import (Lattice, Field, Port, Param, Node, register_node,
                    Registry, Graph, GraphError)
from engine.lattice import stretched_axis


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


def test_particle_domain():
    """粒子域 L1:声明桩注册 + particle_plan 编译 + 求值防御 + 布局列带。"""
    from engine.registry import default_registry
    reg = default_registry()
    for t in ("particle_emitter", "boris_integrator", "leapfrog_integrator",
              "rk4_integrator", "verlet_integrator", "output_encoder"):
        cls = reg.get(t)
        assert cls is not None, f"粒子域节点未注册: {t}"
        assert cls._node_spec.get("domain") == "particle", f"{t} 域标记错误"
    print("✓ 粒子域声明桩已注册(6 类型,domain=particle)")

    g = Graph(reg, Lattice.from_json({"preset": "tiny"}))
    doc = {
        "version": 1, "lattice": {"preset": "tiny"},
        "nodes": [
            {"id": "pe", "type": "particle_emitter",
             "params": {"mode": 1, "v_base": 500.0}},
            {"id": "bi", "type": "boris_integrator",
             "params": {"dt": 0.02, "substeps": 4, "order": 30}},
            {"id": "rk", "type": "rk4_integrator", "params": {"order": 31}},
            {"id": "oe", "type": "output_encoder"},
            {"id": "ob", "type": "output_slot", "params": {"slot": "B"}},
        ],
        "edges": [
            # #28:无 prev/next 链;步进顺序 = order(30 < 31)
            {"from": ["ob", "out"], "to": ["bi", "b"]},
        ],
        "outputs": {},
    }
    g.load_json(doc)
    plan = g.particle_plan()
    kinds = [o["kind"] for o in plan["ops"]]
    assert kinds == ["emitter", "step", "step", "encode"], kinds
    assert plan["slow_path"] is False and plan["count"] == 4
    assert plan["ops"][0]["params"]["v_base"] == 500.0
    assert plan["ops"][1]["kernel"] == "boris"
    assert plan["ops"][1]["slots"]["b"] == "B"
    assert plan["ops"][1]["slots"]["e"] is None
    assert plan["ops"][2]["kernel"] == "rk4"
    print("✓ particle_plan 编译正确(order 排序/内核/槽位解析)")

    # 未知粒子域类型 → slow_path(成本徽标)
    saved = Graph._PARTICLE_OP_KINDS.pop("output_encoder")
    try:
        plan2 = g.particle_plan()
        assert plan2["slow_path"] is True
        assert plan2["count"] == 3  # 未知类型被跳过
    finally:
        Graph._PARTICLE_OP_KINDS["output_encoder"] = saved
    print("✓ 未知粒子域类型 → slow_path 标志")

    # 求值防御:粒子域节点不参与 Python 求值
    try:
        g._eval_node("bi")
        raise AssertionError("粒子域节点应拒绝求值")
    except GraphError as e:
        assert "声明节点" in str(e)
    print("✓ 粒子域节点求值防御")

    # 布局:粒子列带位于场域之后,链内垂直有序
    xs = [g._pos[n][0] for n in ("pe", "bi", "rk", "oe")]
    ys = [g._pos[n][1] for n in ("pe", "bi", "rk", "oe")]
    assert len(set(xs)) == 1, f"粒子链应在同一列: {xs}"
    assert xs[0] > g._pos["ob"][0], "粒子列带应在场域右侧"
    assert ys == sorted(ys), f"粒子链应垂直有序: {ys}"
    print("✓ 粒子域中列带布局(场左→粒子中)")


def test_particle_species():
    """粒子物种节点:三预设填充 + 计划聚合 + 手动编辑转自定义。"""
    from engine.registry import default_registry
    reg = default_registry()
    cls = reg.get("particle_species")
    assert cls is not None and cls._node_spec.get("domain") == "particle"
    presets = cls._node_spec.get("presets")
    assert set(presets) == {"electron", "proton", "alpha"}
    assert abs(presets["electron"]["mass"] - 1.0 / 1836.0) < 1e-15
    assert presets["alpha"]["q"] == 2.0 and presets["alpha"]["mass"] == 4.0
    print("✓ 物种三预设注册(e/p/α,物理值正确)")

    # 加载时按预设填充(JSON 只带 preset 字段)
    g = Graph(reg, Lattice.from_json({"preset": "tiny"}))
    doc = {
        "version": 1, "lattice": {"preset": "tiny"},
        "nodes": [
            {"id": "pe", "type": "particle_emitter"},
            {"id": "se", "type": "particle_species",
             "params": {"preset": "electron", "order": 21}},
            {"id": "sp", "type": "particle_species",
             "params": {"preset": "proton", "order": 22}},
            {"id": "sa", "type": "particle_species",
             "params": {"preset": "alpha", "enabled": False, "order": 23}},
            {"id": "sc", "type": "particle_species", "params": {"order": 24}},
        ],
        "edges": [
            # #28:不再有 prev/next 链;顺序由 order 参数表达(21..24)
            {"from": ["sc", "types"], "to": ["pe", "types"]},
        ],
        "outputs": {},
    }
    g.load_json(doc)
    n_e = g.nodes["se"]
    assert n_e.params["q"] == -1.0 and abs(n_e.params["mass"] - 1 / 1836.0) < 1e-15
    assert n_e.params["name"] == "电子"
    print("✓ 加载即填充预设(JSON 仅 preset 字段)")

    plan = g.particle_plan()
    kinds = [o["kind"] for o in plan["ops"]]
    species = [o for o in plan["ops"] if o["kind"] == "species"]
    assert kinds.count("species") == 4
    by_id = {o["node"]: o for o in species}
    assert by_id["sa"]["params"]["enabled"] is False
    assert by_id["sc"]["params"]["q"] == 1.0  # 默认自定义粒子
    # #28:顺序由显式 order 参数决定(se 21 < sp 22 < sa 23 < sc 24)
    assert [o["node"] for o in species] == ["se", "sp", "sa", "sc"], \
        [o["node"] for o in species]
    assert [o["order"] for o in species] == [21, 22, 23, 24]
    em = next(o for o in plan["ops"] if o["kind"] == "emitter")
    assert em["inputs"].get("types") == "sc"
    print("✓ 计划聚合 4 个物种算子(order 显式排序 + 发射器 types)")

    # 预设切换 + 手动编辑转自定义
    g.set_param("sc", "preset", "alpha")
    assert g.nodes["sc"].params["q"] == 2.0
    assert g.nodes["sc"].params["mass"] == 4.0
    g.set_param("sc", "q", 3.0)
    assert g.nodes["sc"].params["preset"] == "custom"
    print("✓ 预设切换回填 + 手动编辑转 custom")


def test_particle_injection():
    """单粒子注入插件:注册/端口/计划算子/参数透传。"""
    from engine.registry import default_registry
    reg = default_registry()
    cls = reg.get("particle_injection")
    assert cls is not None and cls._node_spec.get("domain") == "particle"
    sp = cls._node_spec["params"]
    assert sp["pos_mode"].choices == ["rll", "xyz"]
    assert sp["vel_mode"].choices == ["vpitch", "vxyz"]
    print("✓ 单粒子注入插件已注册(位置/速度双表示)")

    # 发射器:init 输入端口 + count 图内粒子数
    em = reg.get("particle_emitter")._node_spec
    assert "init" in em["inputs"], "发射器应有 init 注入端口"
    assert "types" in em["inputs"]
    assert em["params"]["count"].default == 0
    assert em["params"]["mode"].max == 3
    print("✓ 发射器:init 端口 + count(0=沿用全局)+ mode≤3")

    g = Graph(reg, Lattice.from_json({"preset": "tiny"}))
    doc = {
        "version": 1, "lattice": {"preset": "tiny"},
        "nodes": [
            {"id": "inj", "type": "particle_injection",
             "params": {"pos_mode": "rll", "r": 6.6, "lat": 0.0, "lon": 0.0,
                        "vel_mode": "vpitch", "v": 400.0, "pitch": 90.0}},
            {"id": "sp", "type": "particle_species", "params": {"preset": "proton"}},
            {"id": "pe", "type": "particle_emitter", "params": {"count": 1}},
            {"id": "bi", "type": "boris_integrator"},
            {"id": "oe", "type": "output_encoder"},
        ],
        "edges": [
            {"from": ["inj", "spec"], "to": ["pe", "init"]},
            {"from": ["sp", "types"], "to": ["pe", "types"]},
        ],
        "outputs": {},
    }
    g.load_json(doc)
    plan = g.particle_plan()
    kinds = [o["kind"] for o in plan["ops"]]
    assert "injection" in kinds, kinds
    inj = next(o for o in plan["ops"] if o["kind"] == "injection")
    assert inj["node"] == "inj"
    assert inj["params"]["pos_mode"] == "rll"
    assert inj["params"]["vel_mode"] == "vpitch"
    assert inj["params"]["pitch"] == 90.0 and inj["params"]["r"] == 6.6
    assert inj["order"] == 25
    emit = next(o for o in plan["ops"] if o["kind"] == "emitter")
    assert emit["params"]["count"] == 1
    assert emit["inputs"]["init"] == "inj"
    print("✓ 计划含 injection 算子 + count=1 + init 指向注入节点")


def test_lattice_axes_full_span():
    """点阵不变量:每个预设轴都必须覆盖完整 [vmin, vmax] 且严格升序。

    回归防线 —— stretched_axis 的外侧点数分配曾把某一侧分成 1 个点,
    而 linspace(0,1,1) 只给出 t=0(与内区端点重合),unique 去重后
    整段外侧消失:tiny 的 y/z 轴只剩 [-3,12] → 表域半宽 3 Re →
    场线追踪 rlim 被封到 2.94 Re(现象:偶极子场线像被关在球里)。
    """
    from engine.lattice import AXIS_PRESETS, LATTICE_PRESETS
    for name, axes in LATTICE_PRESETS.items():
        for ax in ("x", "y", "z"):
            p = AXIS_PRESETS[axes[ax]]
            arr = stretched_axis(**p)
            assert arr.size >= 2, (name, ax, arr.size)
            assert arr[0] == p["vmin"], f"{name}.{ax} 缺负外侧: {arr[0]} != {p['vmin']}"
            assert arr[-1] == p["vmax"], f"{name}.{ax} 缺正外侧: {arr[-1]} != {p['vmax']}"
            assert np.all(np.diff(arr) > 0.0), f"{name}.{ax} 非严格升序"
            # 中心密集区必须在
            inner = arr[(arr >= -p["inner_halfwidth"]) & (arr <= p["inner_halfwidth"])]
            assert inner.size >= 3, f"{name}.{ax} 缺少中心密集区"
            # 表域半宽(rlim 封顶依据)必须与预设范围一致
            dom_half = min(-arr[0], arr[-1])
            assert dom_half >= min(-p["vmin"], p["vmax"]) - 1e-9, (name, ax, dom_half)
    print("✓ 点阵不变量:所有预设轴覆盖完整 [vmin,vmax](含负外侧),域半宽正确")


def test_explicit_order_and_legacy_edges():
    """#28:顺序 = 显式 order 参数;旧图的 prev/next 链边容错跳过。"""
    from engine.registry import default_registry
    reg = default_registry()
    g = Graph(reg, Lattice.from_json({"preset": "tiny"}))

    # (a) 旧图(带 prev/next 链)必须能加载:边被跳过而不是整图拒绝
    legacy = {
        "version": 1,
        "nodes": [
            {"id": "pe", "type": "particle_emitter", "params": {"count": 10}},
            {"id": "bi", "type": "boris_integrator"},
            {"id": "oe", "type": "output_encoder"},
        ],
        "edges": [
            {"from": ["pe", "next"], "to": ["bi", "prev"]},
            {"from": ["bi", "next"], "to": ["oe", "prev"]},
        ],
        "outputs": {},
    }
    g.load_json(legacy)
    assert len(g.skipped_edges) == 2, g.skipped_edges
    assert all("无输入端口 prev" in s["reason"] or "无输出端口 next" in s["reason"]
               for s in g.skipped_edges), g.skipped_edges
    kinds = [o["kind"] for o in g.particle_plan()["ops"]]
    assert kinds == ["emitter", "step", "encode"], kinds
    print("✓ 旧图 prev/next 链边容错跳过(仅记录,不整图拒绝)+ 默认序正确")

    # (b) order 参数决定顺序:把发射器排到最后
    doc = dict(legacy)
    doc["nodes"] = [
        {"id": "pe", "type": "particle_emitter", "params": {"count": 10, "order": 90}},
        {"id": "bi", "type": "boris_integrator", "params": {"order": 5}},
        {"id": "oe", "type": "output_encoder", "params": {"order": 50}},
    ]
    doc["edges"] = []
    g.load_json(doc)
    plan = g.particle_plan()
    assert [o["kind"] for o in plan["ops"]] == ["step", "encode", "emitter"], plan
    assert [o["order"] for o in plan["ops"]] == [5, 50, 90]
    print("✓ 计划顺序 = order 升序(5 步进 → 50 编码 → 90 发射器)")

    # (c) 默认 order(无参数)保持历史语义:发射器 → 步进 → 编码
    g.load_json({"version": 1, "nodes": [
        {"id": "pe", "type": "particle_emitter"},
        {"id": "bi", "type": "boris_integrator"},
        {"id": "oe", "type": "output_encoder"}], "edges": [], "outputs": {}})
    assert [o["kind"] for o in g.particle_plan()["ops"]] == \
        ["emitter", "step", "encode"]
    print("✓ 无 order 参数时按类型默认(10/30/40),与历史链序一致")


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
    test_particle_domain()
    test_particle_species()
    test_particle_injection()
    test_lattice_axes_full_span()
    test_explicit_order_and_legacy_edges()
    print("\n全部冒烟测试通过 ✅")
