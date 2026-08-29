# 重构方案:动态节点化场生成架构

> 项目:EarthMagFieldSim 重构
> 基线:原项目 `mag_field_sim`(C++ Crow + 嵌入式 Python + Three.js)
> 目标:视频剪辑式模块化节点系统,动态加载、现场修改、节点即插件(万物皆插件)

---

## 1. 背景与目标

原项目通过求解相对论洛伦兹力方程,实时模拟带电粒子在地球磁场中的三维动力学。
当前所有物理模块(磁场模型、磁尾、磁层顶、电场、大气、引力、发射器)以
"硬编码开关 + 枚举选择 + 倍率"的形式固化在代码中,任何新模块需要修改 8 处代码。

**历史脉络**(来自 `项目上下文回顾.md` 与 `readme.md`):
- 早期为 Python 方案(FastAPI + pybind11 扩展 `physics_ext.cpp`),因性能不达标
  迁移为 **C++ Crow 服务器 + `physics_engine.cpp` 物理引擎 + 内嵌 Python 桥**;
  `main.py / physics.py / physics_ext.cpp / run_sim.py / launcher.py / build_exe.py`
  等均为已弃用的旧 Python 栈。
- `python_bridge.py` 的场合成链经过多轮研究性重构:直接 B 混合 → 矢量势无散度
  修正 → 晨昏线 sigmoid 平滑 → GSE→GSM 帕克螺旋旋转 → 磁尾铰接(hinging)→
  IGRF 替换为随倾角转动的动态偶极 → 内/外场分离(Shue 磁层顶)→ MSH23 磁鞘模型。
  每次调整都需手术式修改 `_apply_magnetopause_envelope` 这一个巨型函数——
  这正是节点化要消除的痛点。
- 并行研究项目:SWMF/BATSRUS 90 Re 远场 B/E **代理模型**(`PROJECT_PLAN.md`,
  物理基函数 + NN 拟合系数,B=∇×A、E=-u×B)。**该代理模型是节点系统的
  第一等候选节点插件**:作为"代理场模型"节点与 T 系列模型节点并列插拔。

**重构目标**:将"空间电磁场与各力场的生成过程"节点化,引入类视频剪辑软件
(Nuke / DaVinci Resolve / Blender)的节点图模型:

- 动态加载 / 现场添加节点类型(插件文件即节点,无需重启)
- 现场修改参数与逻辑(热重载)
- 节点本身即预设(两层预设:插件文件 = 逻辑预设;图 JSON 片段 = 实例预设)
- 输出槽位自由声明、自动扩展
- 性能红线不变:2 万粒子 × 5 步/帧 × 60 fps

---

## 2. 现状分析

### 2.1 现有架构与数据流

```
浏览器(固定面板UI + Three.js渲染)
   │ 28种硬编码WebSocket消息 + 二进制粒子流(21字节/粒子)
   ▼
C++ Crow服务器(server_main.cpp, 924行)
   │ 巨型 if/else 消息分发 → global_state(JSON) ↔ SimulationEngine 手动同步
   ▼
physics_engine.cpp (940行)           python_bridge.py (876行, 嵌入Python)
   │ Boris积分器(自适应亚步长)           │ compute_grid: 硬编码4步管线
   │ 引力/电场/大气 模块开关+倍率          │  偶极子 → T89/T96/T01/T04/TS05/TA16
   │ 磁力线/电场线追踪(每渲染帧)           │  → 磁尾混合(Harris/Kan) → 磁层顶包络
   │ 三线性插值网格采样(热路径)            │  → Shue边界+IMF+磁鞘+MSH23子进程
```

### 2.2 痛点

1. **8 触点**:新增一个物理模块需同时修改 index.html / main.js 监听 / WS 消息 /
   server_main.cpp 分支 / SimulationEngine 成员+setter / boris_step 热路径 /
   场线追踪 / config.json 同步。
2. 参数微调(如 IMF 角度)触发整管重算(~30 秒),无局部缓存。
3. 模块组合方式被枚举写死,无法表达分支/合并(如两场模型加权求和)。
4. 逻辑不可现场修改,实验新物理必须改 C++ 重新编译。

### 2.3 点阵现状问题(已确认)

现有拉伸点阵 80×72×72:±3 Re 内 0.1 Re 间距(占去 60 点/轴),外层格宽达
8~14 Re。远磁尾 Harris 电流片半厚 ~2 Re,外层仅 1~2 个采样点,磁尾场线与
粒子弹跳轨迹在远磁尾严重失真。**Field 必须支持点阵重构(见 §4.3)。**

---

## 3. 核心设计决策(决策日志)

| # | 决策 | 结论 |
|---|---|---|
| D1 | 节点化边界 | 只节点化场与力场的**生成过程**;粒子受力=查表,节点图不进热路径 |
| D2 | 架构分工 | Python 插件化控制面(图引擎/注册表/热重载)+ C++ 数据面(原生算子/热路径) |
| D3 | 动态性依据 | 场烘焙耗时 99% 在 Fortran/numpy 内核,Python 胶水开销 <1%;同 Nuke/Houdini/Blender 架构 |
| D4 | 一条图两域 | field 域(烘焙期)+ particle 域(实时),唯一跨域边 = 烘焙表 |
| D5 | 参数端口统一 | 输入端口 = 参数 + 插座统一;默认值即滑块,连线即上游数据 |
| D6 | 缓存模型 | field 域节点级内容寻址缓存(昂贵节点=缓存边界);particle 域编译执行计划 |
| D7 | Field 重构 | 点阵下放到字段级,连线自动重采样;输出点阵 128×96×128 细网格 |
| D8 | 原生模块插件化 | C++ 模块注册为原生内核插件:可调参/可启用禁用/可被用户节点替换;逻辑固定 |
| D9 | 槽位替换 | 热路径节点 = 可替换槽位;替换为 Python 节点 = 慢速路径(显式成本徽标) |
| D10 | 输出槽位 | 图 JSON 自由声明,C++ 按名订阅,未知槽位忽略 → 自动扩展 |
| D11 | 用户节点语言 | 用户节点永远 Python 入口,内部可桥接任意语言(项目已有 f2py/子进程先例) |

---

## 4. 目标架构

### 4.1 总览

```
┌─ 控制面:Python 图引擎 ─────────────────────────────────────────────┐
│  统一插件注册表(FieldNode(py) / NativeNode(内核) / 用户节点)        │
│  一条图、两个域;拓扑排序、类型校验、缓存、热重载、两级校验          │
├─ 数据面:C++ 执行计划(sim 线程) ───────────────────────────────────┤
│  原生算子:Boris积分器 / 查表采样器 / 输出编码器 / 场线追踪 / 发射器 │
│  (全部注册为插件;参数/开关/连线热,逻辑固定,可被替换)               │
└───────────────────────────────────────────────────────────────────┘

[日期][Kp][IMF]              ← field 域(烘焙期,秒级)
   ↓     ↓
[T04]→[磁尾]→[包络混合] → B场 ──┐
 ...(E场/阻力场同理)            │ 跨域边:格点表
[发射器]→[粒子缓冲]→[查表采样]→[Boris]→[输出]   ← particle 域(实时)
```

### 4.2 模块分类

| 模块 | 默认实现 | 域 | 执行时机 | 逻辑可热改 |
|---|---|---|---|---|
| 磁场模型 T89~TA16 | Python→Fortran | field | 烘焙 | ✅ |
| 偶极/磁尾/包络/IMF/电场/大气/引力 | Python+numpy | field | 烘焙 | ✅ |
| 粒子发射器(3 种) | Python+numpy(默认) | particle | respawn 一次性 | ✅ |
| 查表采样器 | Native C++ | particle | 每帧热路径 | ❌ |
| Boris 积分器 | Native C++ | particle | 每帧热路径 | ❌ |
| 输出编码器(21B/粒子) | Native C++ | particle | 每帧热路径 | ❌ |
| 磁力线/电场线追踪 | Native C++ | particle | 场更新时 | ❌ |

### 4.3 Field 与点阵设计

```python
Field = { kind: vector|scalar, data: ndarray, id: int, lattice: Lattice }
```

- **点阵下放到字段级**:不再全局共享;每节点声明输出点阵
  (`inherit | declared | coarse | fine | 自定义轴`)
- **连线自动重采样**:点阵不一致的边自动插 ResampleNode(边徽标 "↕");
  scipy 插值 1~2s/次,结果按源字段 id 缓存
- **分层分辨率**:昂贵 Fortran 节点留在粗点阵(~40 万点);
  廉价 numpy 节点(偶极/磁尾/包络/电场/大气)升到细点阵
- **输出点阵**:`128×96×128 ≈ 157 万点`,轴密度按物理需求布点
  (z 轴 ±10 Re 内 0.2 Re 覆盖整条磁尾电流片,再向外拉伸);
  由 `_make_stretched_axis` 泛化而来
- 缓存键加入 lattice:改点阵预设自动标脏

### 4.4 输出槽位自动扩展

- 图 JSON 的 `outputs` 完全自由声明;内建槽位名:`B / E / drag / gravity /
  particles / field_lines`
- C++ 按名订阅:未声明的槽位对应功能自动关闭(启动日志提示);
  引擎不认识的槽位照常烘焙、按名广播,未来消费者自取
- 每槽位独立 seq,烘焙进度按槽位广播

---

## 5. 统一插件 API 规范 v1

### 5.1 目录结构

```
mag_field_sim_refactored/
├── server/            # C++ 数据面:执行计划、原生算子注册表、服务器
├── engine/            # Python 控制面:图引擎、插件注册表、校验、热重载
├── nodes/             # 内置插件(每个 .py = 一个节点类型)
├── user_nodes/        # 用户插件目录(同 type 可覆盖内置)
└── graphs/            # 图 JSON 仓库(预设 = 图文件)
```

### 5.2 插件 = 一个 .py + 一个装饰器

```python
from engine import register_node, Node, Port, Param

@register_node(
    type="t04", name="T04 模型", category="磁场/外部模型", icon="🧲",
    domain="field", impl="python", cost="expensive",
    lattice={"mode": "coarse"},
    inputs={
        "kp": Port("scalar", default=2.0, min=0, max=9, ui="slider"),
        "ps": Port("scalar", default=0.0),
    },
    outputs={"field": "vector_field"},
    params={"enabled": Param("bool", default=True)},
    version=1,
)
class T04Node(Node):
    def compute(self, kp, ps):
        return {"field": Field(bx, by, bz)}   # 纯函数,无副作用
```

- 原生节点(C++ 内核)在 C++ 侧注册同一描述(参数 schema 镜像),
  Python 侧仅有描述符供编辑器渲染,`compute()` 不在 Python 执行
- `cost` 仅作缓存策略标注;`version` 用于迁移钩子

### 5.3 端口类型与连线规则

| 类型 | 内容 | 域 |
|---|---|---|
| `scalar / int / bool / enum / string` | 数值/参数 | 全图 |
| `vector_field / scalar_field` | 点阵矢量/标量场 | field |
| `particle_buffer` | 粒子 SoA(pos/vel/q/m/status/color) | particle |
| `field_table` | 烘焙表引用(跨域) | particle |
| `geometry` | 线集(磁力线/电场线) | particle |

- `scalar → *_field` 广播允许;`field → scalar` 拒绝
- 点阵不一致 → 自动插 ResampleNode
- **跨域唯一通道**:`vector_field → field_table`;其余跨域连线拒绝
- 环检测:Kahn 拓扑排序

### 5.4 节点生命周期

```python
class Node:
    def compute(self, **bound) -> dict: ...     # 必须实现,纯函数
    def validate(self) -> list[str]: ...        # 可选:静态检查,返回警告
    def on_param(self, name, old, new): ...     # 可选:原生节点 → C++ setter
```

### 5.5 图 JSON

```json
{
  "version": 1,
  "lattice": {"preset": "fine", "dims": [128, 96, 128]},
  "nodes": [
    {"id": "n1", "type": "kp_source", "params": {"auto_fetch": true}, "pos": [80, 120]},
    {"id": "n2", "type": "t04", "params": {}, "pos": [260, 120]},
    {"id": "n13", "type": "boris_integrator", "params": {"substep_cap": 20}, "pos": [600, 400]}
  ],
  "edges": [
    {"from": ["n1", "kp"], "to": ["n2", "kp"]},
    {"from": ["n9", "field"], "to": ["n11", "table"]}
  ],
  "outputs": {
    "B": ["n9", "field"], "E": ["n10", "field"], "drag": ["n11", "coef"],
    "particles": ["n13", "buffer"], "field_lines": ["n14", "geometry"]
  }
}
```

### 5.6 缓存与脏传播

- **field 域**:节点级内容寻址缓存,key = `(params, 输入Field.id列表, 输出lattice)`;
  改 IMF 角度只重算 IMF+包络混合,T04 命中缓存
- **particle 域**:无逐帧缓存;执行计划编辑期编译并缓存
- **图版本号**:每次编辑 +1;烘焙请求 = `(graph_version, slots)`;现有 seq 过期机制接管

### 5.7 执行计划(粒子域子图)—— ✅ L1 已落地(2025 重构)

```cpp
struct PlanOp {
    OpKind kind;                  // Emitter / Step / Encode / Respawn(预留)
    std::string node_id;
    EmitterOp emitter;            // 参数镜像 EmitterConfig(节点参数驱动)
    StepOp step;                  // kernel/dt/substeps/max_range/引力/b/e/drag 槽位
    EncodeOp encode;
    RespawnOp respawn;
};
struct Plan { std::vector<PlanOp> ops; bool slow_path; };
```

- 编译链:图 JSON → `Graph.particle_plan()`(引擎权威,链序 = prev/next 拓扑,
  数据端口 → output_slot 槽位名)→ `plancomp::plan_from_json()` → `SimPipeline::set_plan()`
- 运行时 sim 线程顺序执行,**全原生 = 每帧零 Python**;`slow_path` 标记
  (粒子域未知类型)→ 广播 `plan_status` → 前端成本徽标
- **L1 推进内核 seam**(`server/core/advancers.h`):`IBatchAdvancer` + 注册表,
  内置四内核:`boris`(legacy 原样封装,默认图**位级一致**基准)、
  `leapfrog`(Boris 旋转 + 踢-漂-踢)、`rk4`(全经典,对回旋耗散)、
  `verlet`(Boris 旋转 + 位置先行)。**换步进器 = 图上换节点**。
- 关键物理决策:经典核的磁力部分用 **Boris 旋转**(v×B 正交力线性踢
  每步涨能 ~(hω)²/4,200 步可爆 60×;旋转无条件稳定、精确保模);
  E/引力/阻力由各经典格式负责排布。RK4 保留全经典(教科书对照)。
- 无粒子域节点 → `make_default_plan()` 后备计划(行为 = legacy 硬编码
  管线,位级一致);`node.param`(如积分器 dt)热更新 = 计划重编译。
- 未来 L2(DLL SDK):`AdvanceInput` POD 布局即 ABI 边界,extern "C"
  工厂 + 同一虚表约定,封装约百行;未到需要外置原生内核前不实施。

### 5.8 两级校验

| 域 | 校验 | 失败处理 |
|---|---|---|
| field | 粗点阵试烘焙:类型 + 无 NaN/Inf + 量级检查 | 保留旧实现与旧缓存 + 错误徽标 |
| particle | 100 粒子 × 10 步试运行:NaN/发散检查 | 拒绝接入计划 + 错误徽标 |

校验在独立线程执行,不阻塞仿真;校验中节点显示 ⏳。

### 5.9 热重载流程

```
watchdog(nodes/, user_nodes/) 检测 .py 变化
 → importlib.reload → registry.refresh(type)   # 注册表每 type 存 current + previous
 → 重建图中该 type 实例(参数/连线按端口名重绑定)
 → 两级校验
 → 通过:标脏(该节点及下游)→ 自动重烘焙 / 重建计划
 → 失败:回滚到 previous 实现 + 错误徽标
```

- `.pyd` 原生插件:CPython 无法卸载扩展 → 换 .pyd 需重启;参数/开关/连线永远热
- 手动"重新扫描插件"按钮 + 自动 watchdog(可关)

### 5.10 ExpressionNode 沙箱

- 仅 field 域(烘焙期);粒子域禁止(热路径红线)
- `safe_ns = {"np": numpy, "x": X, "y": Y, "z": Z, "r": R}`:无 builtins/import/属性访问
- AST 白名单(算术运算 + np 函数白名单)→ 试烘焙校验
- 用途:UI 里直接写 numpy 表达式实现现场改逻辑

### 5.11 组合节点(最小集)

| 节点 | 端口 | 说明 |
|---|---|---|
| `Add` | a + b | 矢量+矢量、矢量+标量(广播) |
| `Mul` | a × b | 标量倍率、逐格点调制 |
| `Blend` | a、b、w | `w·a + (1-w)·b`,w 可为标量或标量场 |
| `Mask` | 场 + 区域 | 日侧/夜侧/球壳/半径区间掩码 |
| `Resample` | 场 → 场 | 点阵转换(scipy),连线时可自动插入 |

---

## 6. 默认图(复刻现有管线,回归基准)

```
[日期节点]→(倾角ps)                       [Kp源(手动/NOAA)] [IMF极性/帕克角度]
     │                                         │                   │
     ▼                                         ▼                   ▼
[偶极子]──→[内部混合]←──[磁尾(Flaring Harris)]←┘                   │
               │                                                   │
               ▼                                                   ▼
          [包络混合]←────────────────[Tsyganenko模型(T04默认)]←──[Kp]
               │
               ▼
            [B 输出槽]──→[共转电场+对流]──→[E 输出槽]
               │                └──→[Volland-Stern 备选]
               ▼
          [阻力系数输出槽]←──[大气密度模型(单层/分层)]
          [引力场(解析默认,可烘焙)]

[发射器(3模式)]→[粒子缓冲]→[查表采样(B/E/阻力)]→[Boris积分器]→[particles输出]
                                                     ↑
                              [磁力线/电场线追踪]──[field_lines/geometry输出]
```

对应关系:每个节点 = 现 `python_bridge.py` / `physics_engine.cpp` 中的一个函数或
模块分支;每条边 = 现代码里的一次函数调用传参。

---

## 7. 分阶段实施计划

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **0** | 原项目基线提交 + .gitignore + 本方案文档 | 首个 commit 可回退 |
| **1** | Python 引擎骨架(Field/Lattice/Node/Port/Graph/注册表/内容寻址缓存/拓扑+校验);场域节点迁移(python_bridge 各函数搬入 nodes/);默认场图;`graph.bake()` 沿用六列表格式;C++ 改造:`set_magnetic_grid`→`set_field_table(name,...)`,E/阻力改查表,服务器消息改 `graph.upload` | 默认图烘焙结果与原 compute_grid 逐点一致(诊断点回归) |
| **2** | 粒子域原生算子注册(Boris/采样/编码/追踪/发射器)+ 执行计划编译安装 + 槽位替换协议 + Python 慢速路径 | 2 万粒子全原生计划性能与现状持平;Python 替换节点可用 |
| **3** | 前端节点编辑器(LiteGraph.js)+ 属性面板 + 图 JSON 上传/保存 + 成本徽标 + 错误通道 UI | 可视连线可完整复现默认图 |
| **4** | 热重载/ExpressionNode/两级校验完整化;删除 legacy UI 与 28 种旧消息;回归基准(诊断点 + 性能) | 新加一个 Python 插件节点 = 丢文件 + 连线,无需改任何现有代码 |

---

## 8. 性能预算与红线

| 项 | 预算 | 说明 |
|---|---|---|
| 热路径 | 不变:2 万粒子×5 步×60fps | 全原生计划每帧零 Python;查表 = 三线性插值 |
| 烘焙 | 昂贵节点 ≈ 现状(~30s);廉价节点 157 万点 ≈ 2-3s | 局部缓存使大多数参数微调降为秒级 |
| 重采样 | 1~2s/次,按源字段 id 缓存 | scipy |
| 内存 | 场缓存 ≈ 200MB(float64 内部) | 每节点仅保留最近一次结果 |
| 传输 | float32 ≈ 19MB/张(相对精度 1e-7,nT 级误差 ~0.003) | 烘焙后才传,非逐帧 |
| 慢速路径 | 显式成本徽标 + 建议粒子数 ≤ 2000 | Python 粒子节点经 numpy 零拷贝视图 |

**红线**:节点图永不进入粒子热路径(每子步);每帧循环禁止任何 Python 调用(全原生计划)。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 性能退化 | 编译期拓扑 + 烘焙缓存 + 热路径无虚调用;阶段 1 即建 2 万粒子基准 |
| Python/GIL 边界 | Python 只做烘焙;粒子域 Python 算子短时持 GIL 且走慢速路径 |
| 热改逻辑引入崩溃 | 两级校验 + 旧实现回滚 + 旧缓存兜底,仿真永不因改坏逻辑而崩 |
| 重写范围大 | 影子图策略:新旧并存、逐步切换;诊断点回归基准 |
| 前端工程量 | 分三步:后端 API → 自动生成 UI → 可视化画布 |

---

## 10. 实施状态(截至 2026-08,与阶段对照)

| 阶段 | 状态 | 关键产物 |
|---|---|---|
| 0 基线 | ✅ | legacy/ 归档、git 工作流、venv 化(Python 3.14.2)、统一 JSON 日志系统 |
| 1 引擎+场节点 | ✅ | 引擎核心(内容寻址缓存 / any 端口 / output_slot 自动推导 / 渲染域声明节点 / 域感知自动排布)、29+ 场节点(E 场原子分解:convection/corotation/volland_shield + add/mul 组合)、默认图/集成图、**19 诊断点逐位对照(max|Δ|=0.00)**、C++ 烘焙桥与仿真管线 |
| 2 粒子域 | ✅ | C++ 原生热路径(Boris/查表/发射/编码,持久线程池 **0.16ms/步**)+ **L1 图驱动化**:粒子域声明桩(nodes/particle_nodes.py 6 类型)、`Graph.particle_plan()` 计划编译、`IBatchAdvancer` 内核 seam + 四内核(Boris 位级一致 / 蛙跳 / RK4 / 速度Verlet)、Plan 驱动 SimPipeline、图上换节点热切换(端到端测试:上传→计划应用→参数热→内核热) |
| 3 前端 | ✅ | LiteGraph 节点编辑器、属性面板、图上传;**渲染宿主+注册表+渲染项插件化**、内联代码编辑器(网页改 JS 即时生效)、渲染链 UI(渲染域紫色节点+粒子域绿色节点+三域列带) |
| 4 热加载/校验 | ◐ 部分 | 丢文件即注册(场节点+渲染项)+ 回滚安全(渲染项编译失败回退旧实现);ExpressionNode 与两级校验完整化未做(见 §11) |
| 附加 | ✅ | **TRACE_08 C++ 移植**(RK-Merson/三面边界/足点插值/环检测;**偶极解析解验收 r=L·sin²θ 误差 0.0009、273 线 11ms**)、几何帧通道(场线 273 条/槽位 B 端到端)、场线/电场线渲染项(拓扑类三色) |

## 11. 欠账清单(已讨论/已设计,未实现)

| # | 欠账 | 说明 |
|---|---|---|
| D1 | **ExpressionNode** | field 域 numpy 表达式节点(计划 §5.10):AST 白名单沙箱 + 试烘焙校验 |
| D2 | **粒子域节点化(已做 L1)** | ✅ 发射器/积分器(×4)/编码器为图内节点,图驱动执行计划(§5.7);采样器显式节点与 Python 慢速路径算子留待后续 |
| D3 | **两级校验完整化** | engine/validation.py 不存在:场节点"粗点阵试烘焙"、粒子节点"小缓冲试运行"未实现 |
| D4 | user_render_items/ 文件热扫描 | 服务器目录监听 + 前端动态 import(内联编辑器已可用,文件插件路径未通) |
| D5 | 渲染项"存为插件文件"按钮 | 代码编辑器设计了该按钮,未实现(现仅应用/重置) |
| D6 | 渲染域背景色带 | 仅节点着色,画布右侧分区色带未画 |
| D7 | 场线方向箭头 | 参数已留(arrows/arrow_spacing),渲染未实现(legacy 的沿线锥体阵列) |
| D8 | 诊断点渲染项数据帧 | 节点+绑定已接入,服务器不产出 diagnostics 几何帧 |
| D9 | 粒子拖尾渲染项 | legacy 特性未迁移 |
| D10 | MSH23 exe 恢复 | mp_mode=3 目前总回退 mode 2;exe 未入库(robocopy 排除) |
| D11 | TS05/TA16 接入 | 原项目 cp314 pyd 与系统 ABI 匹配,未复制接线 |
| D12 | 图保存/加载到磁盘 UI | 服务器端图仓库(目前仅上传/重置,无持久化) |
| D13 | readme.md 重写 | 仍是旧版文档 |
| D14 | 日志轮转 | logs/server.jsonl 无大小轮转 |
| D15 | 已有节点文件热改的实例重建 | watchdog 只处理新文件;修改已加载节点文件的实例重建流程未接(registry.previous 已备) |
| D16 | 原生节点 SDK | .pyd 逃生舱(nanobind 模板 + 构建脚本) |

## 12. 规划路线图(优先序)

| 优先级 | 方向 | 形态 |
|---|---|---|
| 1 | **子图/复合节点** | 连线图折叠为可复用节点(暴露端口+参数),"节点即预设"终极形态(Nuke Gizmo/Blender Node Group) |
| 2 | **示例图库** | README 五实验(范艾伦带/磁镜/阿尔芬层/极光沉降/磁层拓扑)作为出厂图模板,兼作插件系统高压测试 |
| 3 | ExpressionNode(债务 D1) | 与渲染项内联编辑器对称:左改物理逻辑、右改渲染逻辑 |
| 4 | **代理模型节点** | SWMF 代理模型(ONNX/解析式)作为场节点,与 T 系列并排插拔、同屏 A/B 对比 |
| 5 | 分析/切片渲染项 | 赤道面 \|B\| 剖面、磁层顶线框、L 壳漂移路径叠加(均消费 B/E 表产出几何) |
| 6 | 数据源节点 | omni_source(OMNIWeb 回放)、csv_field_source、satellite_ephemeris → 可复现仿真报告 |
| 7 | 粒子域深化(债务 D2 续) | 采样器显式节点、Python 慢速路径算子(slow_path 落地)、发射器粒子类型列表节点参数 |
| 8 | 插件包格式 | plugin_packs/*.zip(节点.py+渲染项.js+图标+自检样例),拖入即安装 |
| 9 | 原生节点 SDK(债务 D16) | 用户 C++ 内核挂图 |
| 10 | 插件健康徽标 | 面板显示自检通过/警告/失败状态 |

**维护约定**:Python 一律用项目 venv(`.venv`,Python 3.14.2);CMake 钉死
`Python3_EXECUTABLE=3.14`;服务器嵌入解释器优先 venv site-packages;
日志统一走 JSON 日志器(engine.logging / server/core/logger.h / 前端 uiLog);
**重型运行时对象(如 SimPipeline)用 `std::unique_ptr` 按需构造,避免隐式
移动赋值**——MSVC 14.51 对含多向量成员的隐式 move-assign 生成过错误代码
(启动即 0xC0000005,placement-new/unique_ptr 均正常;独立最小复现不触发,
属代码生成问题,见 server_app.cpp Impl 注释);C++ 独立测试用
VS18 vcvars64(`C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\
Auxiliary\Build\vcvars64.bat`)+ `cl /MD /EHsc /O2 /std:c++17 /I..\core`。

**最简预设验收**(graphs/minimal_preset.json + tests/test_components.py,
13 组件逐项验证;前端可视化用 CDP 探针 tests/cdp_*.py + 无头 Edge
`--disable-gpu --enable-unsafe-swiftshader` + vision 复核)。该轮排掉的前端
集成坑,后续改前端务必回归:
1. WS 必须在注册表就绪后连接(boot 竞态 → init_config 的 loadGraph 整图跳过)
2. 渲染项实例 = registry 的 per-node 拷贝,**不得再包一层**(包装对象破坏
   onData 内 this.meshFor 等方法链)
3. 几何帧派发 kind = `"geometry:" + header.kind`(与渲染项 subscribes 约定一致)
4. 粒子 InstancedMesh **每帧重置 count**(否则矩阵区残留旧帧尾巴、计数虚高)
5. 几何帧是烘焙事件驱动的一次性帧,服务器缓存并按新连接**重放**
6. 执行计划变更(发射器/作用半径可能变)→ **全量重生**粒子(只重生死亡
   粒子救不回旧位置整批);粒子沿场线沉降属正确物理,演示需手动 respawn
7. **所有帧坐标统一 Three.js 约定 (x,y,z)→(x,z,-y)**:粒子帧(encoder.h)
   与几何帧(build_geom_frame)必须一致;几何帧漏映射会让 GSM 极轴躺在
   场景 Z 上,磁极横置
