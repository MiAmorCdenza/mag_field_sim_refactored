"""图:节点实例、连线、命名输出、拓扑校验、拉取式求值与内容寻址缓存。

机制(REFACTOR_PLAN §5.6):
- 拉取式求值:从输出槽递归回溯输入
- 内容寻址缓存:每节点缓存最近一次 (key -> outputs),
  key = (params, {输入端口: 值签名});Field 签名 = (id, lattice)
  → 上游结果不变即命中,无需显式脏传播
- 图版本号:每次编辑 +1(烘焙请求携带,seq 过期机制沿用)
- 类型规则:标量族互连;scalar → scalar_field 广播填充;
  scalar → vector_field 拒绝(语义歧义,由节点自声明标量端口处理)
"""
from __future__ import annotations

import itertools

import numpy as np

from .field import Field
from .ports import SCALAR_TYPES, FIELD_TYPES, coerce_scalar


class GraphError(Exception):
    """图构建/求值错误。"""


def _compatible(src_type, dst_type):
    if dst_type == src_type:
        return True
    if dst_type == "any" or src_type == "any":
        return True  # 通用透传端口(输出节点等)
    if dst_type in SCALAR_TYPES and src_type in SCALAR_TYPES:
        return True
    if dst_type == "scalar_field" and src_type in SCALAR_TYPES:
        return True  # 广播填充
    return False


def _clamp(value, port):
    if port.min is not None and value < port.min:
        value = port.min
    if port.max is not None and value > port.max:
        value = port.max
    return value


def _sig(value):
    if isinstance(value, Field):
        return ("f", value.id, id(value.lattice))
    return ("s", type(value).__name__, repr(value))


class Graph:
    def __init__(self, registry, lattice=None):
        self.registry = registry
        self.lattice = lattice
        self.nodes = {}       # node_id -> Node
        self.inputs_map = {}  # (dst_id, dst_port) -> (src_id, src_port)
        self.outputs = {}     # 槽位名 -> (node_id, port)
        self._pos = {}        # node_id -> [x, y](编辑器坐标)
        self._cache = {}      # node_id -> (key, outputs)
        self._seq = itertools.count(1)
        self.version = 0      # 图版本号(每次编辑 +1)

    # ================= 构建与编辑 =================
    def load_json(self, doc):
        if not isinstance(doc, dict):
            raise GraphError("图 JSON 必须是对象")
        if self.lattice is None and doc.get("lattice"):
            from .lattice import Lattice
            self.lattice = Lattice.from_json(doc["lattice"])
        self.nodes.clear()
        self.inputs_map.clear()
        self.outputs.clear()
        self._pos.clear()
        self._cache.clear()

        for nd in doc.get("nodes", []):
            self.add_node(nd["id"], nd["type"],
                          nd.get("params"), nd.get("pos"),
                          nd.get("input_defaults"))
        for e in doc.get("edges", []):
            self.connect(e["from"][0], e["from"][1], e["to"][0], e["to"][1])
        for name, ref in (doc.get("outputs") or {}).items():
            self.declare_output(name, ref[0], ref[1])
        # 自动推导:图中每个输出角色节点(role="output",如 output_slot)
        # = 一个命名输出槽(最终渲染环节显式化:Nuke/Blender 式 OutputNode)
        for node_id, node in self.nodes.items():
            spec = node.spec()
            if spec.get("role") == "output" or spec.get("type") == "output_slot":
                slot = node.params.get("slot", "unnamed")
                if slot not in self.outputs:
                    self.declare_output(slot, node_id, "out")
        # 自动排布:存在缺位置的节点(如内置默认图)时做层次化布局
        if any(nid not in self._pos for nid in self.nodes):
            self.auto_layout()
        self._check_acyclic()
        self.version += 1
        return self

    def add_node(self, node_id, node_type, params=None, pos=None,
                 input_defaults=None):
        if node_id in self.nodes:
            raise GraphError(f"节点 id 重复: {node_id}")
        cls = self.registry.get(node_type)
        if cls is None:
            raise GraphError(f"未知节点类型: {node_type}")
        node = cls(node_id, params)
        node.graph = self
        if input_defaults:
            node.input_defaults = dict(input_defaults)
        self.nodes[node_id] = node
        if pos:
            self._pos[node_id] = pos
        self.version += 1
        return node

    def remove_node(self, node_id):
        if node_id not in self.nodes:
            raise GraphError(f"节点不存在: {node_id}")
        self.nodes.pop(node_id, None)
        self.inputs_map = {k: v for k, v in self.inputs_map.items()
                           if k[0] != node_id and v[0] != node_id}
        self.outputs = {n: ref for n, ref in self.outputs.items()
                        if ref[0] != node_id}
        self._pos.pop(node_id, None)
        self._cache.pop(node_id, None)
        self.version += 1

    def connect(self, src_id, src_port, dst_id, dst_port):
        src = self.nodes.get(src_id)
        dst = self.nodes.get(dst_id)
        if src is None or dst is None:
            raise GraphError("连线端点不存在")
        sspec = src.spec()["outputs"]
        dspec = dst.spec()["inputs"]
        if src_port not in sspec:
            raise GraphError(f"{src_id} 无输出端口 {src_port}")
        if dst_port not in dspec:
            raise GraphError(f"{dst_id} 无输入端口 {dst_port}")
        st, dt = sspec[src_port], dspec[dst_port].ptype
        if not _compatible(st, dt):
            raise GraphError(f"端口类型不兼容: {st} → {dt}")
        self.inputs_map[(dst_id, dst_port)] = (src_id, src_port)
        self.version += 1

    def disconnect(self, dst_id, dst_port):
        self.inputs_map.pop((dst_id, dst_port), None)
        self.version += 1

    def set_param(self, node_id, name, value):
        """设置参数;输入端口参数写入 input_defaults,其余走 on_param 钩子。"""
        node = self.nodes.get(node_id)
        if node is None:
            raise GraphError(f"节点不存在: {node_id}")
        spec = node.spec()
        if name in spec["inputs"]:
            port = spec["inputs"][name]
            node.input_defaults[name] = _clamp(coerce_scalar(port.ptype, value),
                                               port)
        elif name in spec.get("params", {}):
            p = spec["params"][name]
            value = _clamp(coerce_scalar(p.ptype, value), p)
            old = node.params.get(name)
            node.params[name] = value
            node.on_param(name, old, value)
        else:
            raise GraphError(f"{node_id} 无参数 {name}")
        self.version += 1

    def declare_output(self, name, node_id, port):
        """声明命名输出槽位(自动扩展:图 JSON 自由声明)。"""
        node = self.nodes.get(node_id)
        if node is None:
            raise GraphError(f"输出引用节点不存在: {node_id}")
        if port not in node.spec()["outputs"]:
            raise GraphError(f"{node_id} 无输出端口 {port}")
        self.outputs[name] = (node_id, port)
        self.version += 1

    def set_lattice(self, lattice):
        """更换点阵:结构性变化,清空全部缓存。"""
        self.lattice = lattice
        self._cache.clear()
        self.version += 1

    def auto_layout(self, gap_x=240.0, gap_y=110.0):
        """域感知层次化排布:
        - 场域(左):拓扑深度定列,同列重心排序,汇节点右对齐
        - 粒子域(中):单列垂直链(发射器→积分器→编码器,沿链边排布)
        - 渲染域(右):单列垂直链(渲染管线起始在最上,沿链边排布)
        - 孤立数据节点排在数据域最后一列之后
        """
        from collections import deque

        def domain_of(nid):
            return self.nodes[nid].spec().get("domain", "field")

        render_nodes = [n for n in self.nodes if domain_of(n) == "render"]
        particle_nodes = [n for n in self.nodes if domain_of(n) == "particle"]
        data_nodes = [n for n in self.nodes
                      if domain_of(n) not in ("render", "particle")]

        # ---- 全图邻接(渲染链 BFS 用) ----
        adj_all = {nid: [] for nid in self.nodes}
        for (dst, _), (src, _) in self.inputs_map.items():
            adj_all[src].append(dst)

        # ---- 数据域层次排布 ----
        indeg = {n: 0 for n in data_nodes}
        adj = {n: [] for n in data_nodes}
        for (dst, _), (src, _) in self.inputs_map.items():
            if dst in adj and src in adj:
                adj[src].append(dst)
                indeg[dst] += 1

        depth = {}
        queue = deque([n for n in data_nodes if indeg[n] == 0])
        for n in queue:
            depth[n] = 0
        while queue:
            n = queue.popleft()
            for m in adj[n]:
                depth[m] = max(depth.get(m, -1), depth[n] + 1)
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
        for n in data_nodes:
            depth.setdefault(n, 0)

        # 汇节点(无下游)统一钉到最右列:终端对齐
        sinks = [n for n in data_nodes if not adj[n]]
        if sinks:
            maxd = max(depth.values())
            for n in sinks:
                depth[n] = maxd

        cols = {}
        for n, d in depth.items():
            cols.setdefault(d, []).append(n)

        def sort_key(n):
            ups = [s for (d2, _), (s, _) in self.inputs_map.items()
                   if d2 == n and s in depth]
            if not ups:
                return (-1.0, 0)  # 源节点置顶
            return (sum(depth.get(u, 0) for u in ups) / len(ups), 0)

        for d in cols:
            cols[d].sort(key=sort_key)

        connected = set()
        for (d2, _), (s, _) in self.inputs_map.items():
            connected.add(d2)
            connected.add(s)
        orphans = [n for n in data_nodes if n not in connected]

        max_col = max((len(c) for c in cols.values()), default=0)
        x = 0.0
        for d in sorted(cols):
            col = cols[d]
            y0 = 60.0 + (max_col - len(col)) / 2.0 * gap_y
            for i, n in enumerate(col):
                self._pos[n] = [x, y0 + i * gap_y]
            x += gap_x
        for i, n in enumerate(orphans):
            self._pos[n] = [x, 60.0 + i * gap_y]
        if orphans:
            x += gap_x

        # ---- 粒子域:中列垂直链(发射器→积分器→编码器,与渲染链同约定) ----
        pchain = []
        pseen = set()
        starts = [n for n in particle_nodes
                  if not any(s in particle_nodes
                             for (_d2, _), (s, _) in self.inputs_map.items()
                             if _d2 == n)]
        queue = deque(starts or ([particle_nodes[0]] if particle_nodes else []))
        while queue:
            n = queue.popleft()
            if n in pseen:
                continue
            pseen.add(n)
            pchain.append(n)
            for m in adj_all[n]:
                if m in particle_nodes and m not in pseen:
                    queue.append(m)
        for n in particle_nodes:
            if n not in pseen:
                pchain.append(n)
        if pchain:
            for i, n in enumerate(pchain):
                self._pos[n] = [x, 60.0 + i * gap_y]
            x += gap_x

        # ---- 渲染域:右侧单列垂直链 ----
        chain = []
        seen = set()
        starts = [n for n in render_nodes
                  if self.nodes[n].spec().get("type") == "render_pipeline_start"]
        queue = deque(starts or ([render_nodes[0]] if render_nodes else []))
        while queue:
            n = queue.popleft()
            if n in seen:
                continue
            seen.add(n)
            chain.append(n)
            for m in adj_all[n]:
                if domain_of(m) == "render" and m not in seen:
                    queue.append(m)
        for n in render_nodes:
            if n not in seen:
                chain.append(n)
        for i, n in enumerate(chain):
            self._pos[n] = [x, 60.0 + i * gap_y]
        self.version += 1

    def to_json(self):
        edges = [{"from": list(src), "to": list(dst)}
                 for dst, src in self.inputs_map.items()]
        nodes = []
        for nid, n in self.nodes.items():
            nd = {"id": nid, "type": n.spec()["type"], "params": dict(n.params)}
            if n.input_defaults:
                nd["input_defaults"] = dict(n.input_defaults)
            if nid in self._pos:
                nd["pos"] = self._pos[nid]
            nodes.append(nd)
        return {
            "version": 1,
            "lattice": self.lattice.to_json() if self.lattice else None,
            "nodes": nodes,
            "edges": edges,
            "outputs": {name: list(ref) for name, ref in self.outputs.items()},
        }

    def _check_acyclic(self):
        indeg = {nid: 0 for nid in self.nodes}
        adj = {nid: [] for nid in self.nodes}
        for (dst, _), (src, _) in self.inputs_map.items():
            adj[src].append(dst)
            indeg[dst] += 1
        queue = [n for n, d in indeg.items() if d == 0]
        seen = 0
        while queue:
            n = queue.pop()
            seen += 1
            for m in adj[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
        if seen != len(self.nodes):
            raise GraphError("图存在环,拒绝加载")

    # ================= 渲染域 =================
    def render_bindings(self):
        """渲染域绑定表(声明节点 → 数据契约)。

        返回 [{node_id, type, params, inputs: {端口: [上游节点, 上游端口]}}]
        供服务器编译数据通道:对绑定场运行对应数据源(追踪/采样/编码),
        产出帧,通道名 = 渲染节点 id。
        """
        out = []
        for nid, node in self.nodes.items():
            if node.spec().get("domain") != "render":
                continue
            ins = {}
            for (dst, dport), (src, sport) in self.inputs_map.items():
                if dst == nid:
                    ins[dport] = [src, sport]
            out.append({
                "node_id": nid,
                "type": node.spec()["type"],
                "params": dict(node.params),
                "inputs": ins,
            })
        return out

    # ================= 粒子域 =================
    _PARTICLE_OP_KINDS = {
        "particle_emitter": "emitter",
        "particle_species": "species",
        "boris_integrator": "step",
        "leapfrog_integrator": "step",
        "rk4_integrator": "step",
        "verlet_integrator": "step",
        "output_encoder": "encode",
    }

    def particle_plan(self):
        """粒子域执行计划(C++ 原生管线消费,L1)。

        返回 {"ops": [...], "slow_path": bool, "count": n}
        - 顺序 = 粒子域链拓扑(prev/next 边):发射器 → 积分器 → 编码器
        - 数据端口(b/e/drag)→ 槽位名:上游 output_slot 的 slot 参数,
          或 outputs 中声明该节点的槽位;未连接 = None
        - step 算子的 kernel = 类型名去 "_integrator" 后缀
        - 粒子域内未知节点类型 → 该节点跳过并置 slow_path(成本徽标)
        """
        pnodes = [nid for nid, n in self.nodes.items()
                  if n.spec().get("domain") == "particle"]
        indeg = {n: 0 for n in pnodes}
        adj = {n: [] for n in pnodes}
        for (dst, _), (src, _) in self.inputs_map.items():
            if dst in adj and src in adj:
                adj[src].append(dst)
                indeg[dst] += 1
        queue = [n for n in pnodes if indeg[n] == 0]
        order = []
        while queue:
            n = queue.pop(0)
            order.append(n)
            for m in adj[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
        for n in pnodes:
            if n not in order:  # 环已在 load_json 拒绝;防御兜底
                order.append(n)

        def slot_of(nid):
            """节点输出 → 槽位名(output_slot 或 outputs 声明)。"""
            node = self.nodes.get(nid)
            if node is None:
                return None
            if node.spec().get("type") == "output_slot":
                return node.params.get("slot", "unnamed")
            for name, (sid, _sport) in self.outputs.items():
                if sid == nid:
                    return name
            return None

        ops = []
        slow = False
        for nid in order:
            node = self.nodes[nid]
            t = node.spec()["type"]
            kind = self._PARTICLE_OP_KINDS.get(t)
            if kind is None:
                slow = True  # 未知粒子域节点:不编译,成本徽标
                continue
            ins = {}
            for (dst, dport), (src, _sport) in self.inputs_map.items():
                if dst == nid:
                    ins[dport] = src
            # 参数 = 规格默认值 + 实例覆盖(JSON 未显式给出的用默认,
            # 如物种节点的 q/mass/enabled)
            pdefaults = {k: p.default
                         for k, p in node.spec()["params"].items()}
            pmerged = dict(pdefaults)
            pmerged.update(node.params)
            op = {"kind": kind, "node": nid, "type": t,
                  "params": pmerged, "inputs": ins}
            if kind == "step":
                op["kernel"] = t[:-len("_integrator")]
                op["slots"] = {
                    "b": slot_of(ins["b"]) if ins.get("b") else None,
                    "e": slot_of(ins["e"]) if ins.get("e") else None,
                    "drag": slot_of(ins["drag"]) if ins.get("drag") else None,
                }
            ops.append(op)
        return {"ops": ops, "slow_path": slow, "count": len(ops)}

    # ================= 求值与烘焙 =================
    def _node_lattice(self, node_id):
        """节点有效点阵(v1:图级单点阵;节点级点阵为后续优化)。"""
        if self.lattice is None:
            raise GraphError("图未设置点阵,无法计算格点场")
        return self.lattice

    def evaluate(self, output_names=None):
        names = list(self.outputs) if output_names is None else output_names
        missing = [n for n in names if n not in self.outputs]
        if missing:
            raise GraphError(f"图未声明输出槽: {missing}")
        return {name: self._eval_node(nid)[port]
                for name, (nid, port) in self.outputs.items() if name in names}

    def _eval_port(self, node_id, port):
        """求某节点某端口的值:有连线 → 上游;否则 → 端口默认值。"""
        key = (node_id, port)
        if key in self.inputs_map:
            return self._eval_port(*self.inputs_map[key])
        node = self.nodes[node_id]
        spec = node.spec()
        if port in spec["inputs"]:
            p = spec["inputs"][port]
            return node.input_defaults.get(port, p.default)
        if port in spec["outputs"]:
            return self._eval_node(node_id)[port]
        raise GraphError(f"{node_id} 端口 {port} 无来源")

    def _eval_node(self, node_id):
        node = self.nodes[node_id]
        spec = node.spec()
        if spec.get("domain") in ("render", "particle"):
            label = {"render": "渲染域", "particle": "粒子域"}[spec.get("domain")]
            raise GraphError(
                f"{label}节点 {node_id}({spec.get('type')})是声明节点,"
                f"不参与数值求值")

        # 1) 收集原始输入(广播前)
        raw_inputs = {}
        for pname in spec["inputs"]:
            raw_inputs[pname] = self._eval_port(node_id, pname)

        # 2) 内容寻址缓存:键 = 参数 + 点阵身份 + 原始输入签名
        #    (广播场无 id,不得进键;标量按值签名,场按 id 签名)
        key = (frozenset(node.params.items()),
               id(self._node_lattice(node_id)),
               tuple(sorted((pname, _sig(v)) for pname, v in raw_inputs.items())))
        hit = self._cache.get(node_id)
        if hit is not None and hit[0] == key:
            return hit[1]

        # 3) 广播(标量 → 标量场,在键计算之后;None 表示可选场未连接)
        inputs = {}
        for pname, p in spec["inputs"].items():
            v = raw_inputs[pname]
            if p.ptype in FIELD_TYPES and v is not None and not isinstance(v, Field):
                v = self._broadcast(v, p.ptype, self._node_lattice(node_id))
            inputs[pname] = v

        # 4) 计算 + 包装(标量输出强制类型;场输出包 ndarray 并赋新 id)
        raw = node.compute(**inputs) or {}
        outputs = {}
        for oname, otype in spec["outputs"].items():
            if oname not in raw:
                raise GraphError(f"{node_id} 未提供输出 {oname}")
            outputs[oname] = self._wrap(raw[oname], otype,
                                        self._node_lattice(node_id), self._seq)
        self._cache[node_id] = (key, outputs)
        return outputs

    @staticmethod
    def _broadcast(value, ptype, lattice):
        """标量 → 标量场:全点阵填充。"""
        data = np.full((lattice.nx, lattice.ny, lattice.nz),
                       float(value), dtype=np.float64)
        return Field("scalar", data, lattice)

    @staticmethod
    def _wrap(value, otype, lattice, seq=None):
        if otype == "any":
            # 通用透传:输出节点原样转发(Field 仍赋新 id 以维持缓存语义)
            if isinstance(value, Field):
                return Field(value.kind, value.data, value.lattice,
                             field_id=None if seq is None else next(seq))
            return value
        if otype in SCALAR_TYPES:
            return coerce_scalar(otype, value)
        if otype in FIELD_TYPES:
            if isinstance(value, Field):
                # 节点直接返回的 Field:克隆并赋新 id(内容寻址缓存的关键)
                return Field(value.kind, value.data, value.lattice,
                             field_id=None if seq is None else next(seq))
            arr = np.asarray(value, dtype=np.float64)
            expect = (lattice.nx, lattice.ny, lattice.nz)
            if otype == "vector_field":
                if arr.shape != expect + (3,):
                    raise GraphError(f"矢量场形状错误: {arr.shape} != {expect + (3,)}")
                return Field("vector", arr, lattice,
                             field_id=None if seq is None else next(seq))
            if arr.shape != expect:
                raise GraphError(f"标量场形状错误: {arr.shape} != {expect}")
            return Field("scalar", arr, lattice,
                         field_id=None if seq is None else next(seq))
        return value  # particle_buffer / field_table / geometry(阶段 2)

    def bake(self, output_names=None):
        """烘焙命名输出为传输格式(兼容旧六列表 + 标量场)。

        返回 {槽位名: {"xs"/"ys"/"zs"/"bx"/"by"/"bz"} 或 {"...","scalar"}}
        """
        result = {}
        for name, val in self.evaluate(output_names).items():
            if val is None:
                raise GraphError(
                    f"输出槽「{name}」无有效值:检查对应的 output_slot "
                    f"节点是否已连线场源")
            if isinstance(val, Field):
                lat = val.lattice
                base = {"xs": lat.xs.tolist(), "ys": lat.ys.tolist(),
                        "zs": lat.zs.tolist()}
                if val.kind == "vector":
                    base["bx"] = val.data[..., 0].ravel().tolist()
                    base["by"] = val.data[..., 1].ravel().tolist()
                    base["bz"] = val.data[..., 2].ravel().tolist()
                else:
                    base["scalar"] = val.data.ravel().tolist()
                result[name] = base
            else:
                result[name] = val
        return result
