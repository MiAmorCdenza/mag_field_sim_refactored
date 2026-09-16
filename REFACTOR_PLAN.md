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
- **粒子物种声明节点**(`particle_species`,OpKind::Species):一个节点 =
  一个物种,元素参照老版 particle_types(name/q/mass/v_mult/weight/
  color/checked→enabled),预设 electron/proton/alpha 下拉自动回填
  (引擎 on_param + 前端 spec.presets 同表);计划编译聚合全部启用的
  物种 → 发射器类型列表,无物种节点时沿用服务器默认。
- **单粒子注入节点**(`particle_injection`,OpKind::Injection):确定性
  初条件(零随机),接发射器 `init` 端口即切 mode 3。位置 (r,lat,lon)
  或 (x,y,z);速度 (v,俯仰角,回旋相位)**相对局部 B**(B 表由
  SimPipeline 注入 `set_field`;无表退化 z 轴)或 (vx,vy,vz)。
  发射器 `count` = 图内粒子数覆盖(0 = 沿用全局)。
  **初条件预览两级**:L1 本地(editor.js + `renderer/items/source_preview.js`,
  拖滑杆即时刷新、零带宽);**L2 服务器**(计划应用/烘焙后广播
  `source_preview`:位置 + 局部 B(nT)+ 速度方向 + R_g + 回旋周期,
  数学与生成共用 emitters.h 的 `injection_position`/`injection_velocity`,
  故与发射器逐位一致;标量用积分器常数 31200 nT/表单位、2988.5959
  换回物理量)。前端属性面板显示读数、3D 画 v̂(绿)+ b̂(蓝)双箭头。
  L3(计划)预测轨道轨迹(用表场积分若干周期画弹跳/漂移路径)。
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
| D2 | **粒子域节点化(已做 L1)** | ✅ 发射器/积分器(×4)/编码器/**粒子物种**为图内节点,图驱动执行计划(§5.7);采样器显式节点与 Python 慢速路径算子留待后续 |
| D3 | **两级校验完整化** | engine/validation.py 不存在:场节点"粗点阵试烘焙"、粒子节点"小缓冲试运行"未实现 |
| D4 | user_render_items/ 文件热扫描 | 服务器目录监听 + 前端动态 import(内联编辑器已可用,文件插件路径未通) |
| D5 | 渲染项"存为插件文件"按钮 | 代码编辑器设计了该按钮,未实现(现仅应用/重置) |
| D6 | 渲染域背景色带 | 仅节点着色,画布右侧分区色带未画 |
| D7 | 场线方向箭头 | 参数已留(arrows/arrow_spacing),渲染未实现(legacy 的沿线锥体阵列) |
| D8 | 诊断点渲染项数据帧 | 节点+绑定已接入,服务器不产出 diagnostics 几何帧 |
| D9 | 粒子拖尾渲染项 | ✅ 已实现(renderer/items/trails.js):客户端从已收帧推导,**零额外带宽**;单 LineSegments+vertexColors 全色一次 draw call,id 变化重置/死亡冻结 |
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
**启动与演示走 `scripts\start.bat`(或 start.ps1)**:自动完成 venv 创建/
依赖安装/CMake 配置编译/端口预检/启动/开浏览器;环境审计走
`scripts\check_env.ps1`。注意 .ps1/.bat 必须存为 **UTF-8 with BOM**
(PowerShell 5.1 对无 BOM 文件按 GBK 解析,中文会炸);
**重型运行时对象(如 SimPipeline)用 `std::unique_ptr` 按需构造,避免隐式
移动赋值**;`Emitter` 同理(含 mt19937 5000B 状态)——已改为**显式移动
构造/赋值**。MSVC 14.51 对含多向量/大状态成员的类生成过错误代码
(启动即 0xC0000005,独立最小复现不触发,属代码生成问题,见
server_app.cpp Impl 注释与 emitters.h);C++ 独立测试用
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
8. **LiteGraph any 端口必须用通配类型 `"*"`(非颜色字符串)**:v0.4 的
   isValidConnection 对非空类型严格相等,any 用颜色会让 vector_field→any
   等连线被 connect 静默拒绝 → 编辑器往返丢边 → 服务器侧"输出槽未连接
   场源"(实测默认图 26 边往返丢 6 边,全是穿过 output_slot 的边)
9. **NOMINMAX 必须在 winsock2.h 之前**(winsock2 自身包含 windows.h)
10. **服务器启动前做端口占用预检**:Windows SO_REUSEADDR 允许双进程绑
    同端口,请求会随机落到两个实例(已踩坑,见 main.cpp)
11. **stretched_axis 外侧两处退化都要防**:(a) `_side` 对负 span(start>end)
    曾判 `span<=0` 返回空 → 所有点阵缺 x<-3/y<-3/z<-3(磁尾从没进过表),
    左外侧是"降序列",不是删掉;(b) **某一侧只分到 1 个点时**
    `linspace(0,1,1)` 只有 t=0 → 退化成与内区端点重合的一点,`unique`
    去重后**整段外侧消失**(tiny 的 y/z 轴因此只剩 [-3,12],域半宽
    dom_half=3 → rlim=2.94 → 偶极子场线像被关在半径 3 Re 的球里)。
    n==1 必须返回**远端**。不变量测试:test_engine_smoke.py
    `test_lattice_axes_full_span`(逐预设断言轴覆盖完整 [vmin,vmax])
12. **默认图用 coarse 点阵**(legacy 视场,烘焙 ~12s 属"离线秒级"契约);
    tiny 留给测试预设;发射器默认 max_range=24 与域一致(域外采样
    钳到边界值,物理失真)
13. **改 core/*.h 后必须全量重编**:ninja 头文件依赖有盲区,只重编部分
    TU 会造成跨 TU 结构布局不一致(ODR),症状是启动即 0xC0000005、
    崩溃栈停在 VCRUNTIME memcpy + 工作线程。做法:
    `Get-ChildItem src\*.cpp | % { $_.LastWriteTime = Get-Date }` 再 build
14. **新前端渲染项要两处登记**:`renderer/items/*.js` + `index.html` 脚本,
    并在 `graphs/default_graph.json` 与 server_app 内置默认图**两处**
    都加渲染节点与链边(否则实例化不了、视口无效果)
15. **节点标题必须在构造器里给定**:`LGraphNode.call(this, "")` 会落到
    LiteGraph 的 `title || "Unnamed"` 回退,而 `registerNodeType` 只写**类级**
    `T.title`(画布读实例 `this.title`)→ 曾导致整图节点全显示 "Unnamed"。
    载入时 `nd.title || 插件名`;导出只在用户改过标题时写 `title`
16. **别用 LiteGraph 自带左下角覆盖层判断运行状态**:它画的是
    `graph.globaltime/iteration/fps`,属它自己的 `runStep` 执行循环,
    本项目从不调用 → **恒为 0**,极易误判"卡死"。实时统计放 **DOM 覆盖层**
    `#sim-hud`(protocol.js 250ms 定时器刷新);`canvas.renderInfo` 置空。
    注意**不要**用 canvas 覆盖层做实时 HUD:它只在画布重绘时更新
    (曾因此"假实时"——截图显示 t=0 而真实值是 596 s)
17. **仿真时间来自帧头 `t`**(server_app 每帧写 `pipeline->sim_time()`,
    名义步进累积 `Σ dt×substeps`),`reset_sim_time()` 只在 `graph.upload`
    调用 —— 调参重编译计划**不重置**,便于观察连续演化
18. **单粒子预览与生成共用同一套数学**(emitters.h 的
    `injection_position` / `injection_velocity`):预览另写一套必然漂移。
    `headless.exe` 第 7 节断言"预览速度 == 生成速度(逐位)";
    预览还镜像了生成路径的两处钳制(r<1.05 抬升、v≥c 钳制),否则
    读数与实际粒子不符
19. **事件型文本帧(如 source_preview)必须缓存并按新连接重放**,
    否则后连的页面永远收不到(只在事件点广播一次)。缓存字段
    `st.source_preview_json`,与几何帧 `st.geom_cache` 同机制,
    `graph.upload` 时一并作废
20. **表插值 vs 解析场**:偶极场 ∝1/r³ 凸 → 三线性插值在格点间**偏高**,
    且**场方向只依赖 r̂**(磁轴附近 B∥r̂ → 极盖场线是笔直射线,到表域
    边界硬终止;偶极子倾 0.5 rad 时 lon≈0 的极盖种子距磁极轴仅 1.4–18.6°,
    "外围一圈直射线"是正确几何而非伪影)。格距必须与外层跨度匹配:
    `tiny` 原 x32/y,z28 点 → 外层 y/z 每轴只剩 ±12 两点,近磁轴线与解析解
    偏差 3–8 Re、部分提前折回地球,|B|(6.6,0,0) 偏高 65%;
    加密到 x56/y,z48(格距 ~1 Re)→ 偏差 ≤0.24 Re、|B| 误差 +2.5%,
    烘焙 30→56 ms。**`coarse`/`legacy` 粗轴是 legacy 位级一致的对照基准,
    冻结不改**(诊断点对照 max|Δ|=0.00e+00 依赖它)
21. **几何帧 v2 = 每点带场强**(`build_geom_frame`):16 B/点
    `(f32 x,y,z, f32 |F|)`,meta 带 `v/unit/smin/smax`;v1(12 B/点、无场强)
    仍可解析(前端按 `meta.v` 选 stride)—— 协议加字段必须留旧版解析路径。
    `|F|` 是**渲染单位**:B 表 ×31200 → nT,E 表原样(归一化)。
    `FieldLine.bmag` 由 tracer 每点一次查表填入(相对每步 5 次 RK 采样可忽略),
    双向拼接时与点数组同步合并,足点插值处一并修正
22. **场线着色三模式**(`color_mode` = class / bmag / reason):class 是
    **种子拓扑类别**(0 赤道闭合/1 极盖开放/2 上游太阳风,追踪时打标),
    bmag 用 viridis+log 顶点色,reason 是终止原因(落地/出域/绕圈/点数上限/
    场近零)。**不要以为颜色跟 |B| 相关**:偶极子里两者恰好单调同向(闭合线
    在强场内区、开放线扫向弱场外围),换 T89/磁尾就解耦(开放线起点在极区
    强场)。图例写在视口右上 `#line-legend`(渲染项直写 DOM)
23. **渲染域参数必须"改即推"**:属性面板 onChange 里要显式
    `pushRenderParams(node)` —— 之前只在 `renderProps`(选中/重建面板)时推,
    改 color_mode 看不到任何反应,必须等下一次几何帧。另:线类渲染项的
    `color` 默认必须是 `""`(空 = 用 color_mode),否则新建节点会被默认色
    静默覆盖分类色;`pushRenderParams` 也不推空 color
24. **`node.param` 必须同步权威图 JSON**:只更新 Python 侧图 + 计划,不刷新
    `st.graph_json` → 新连接的 `init_config`、以及「重置为服务器图」都会
    发**旧参数**(实测:滑块把 count 改成 42779,新连接拿到的还是 1)。
    现在 handler 里一并 `bridge.graph_json(gjson)` 写回
25. **注入节点 + count>1 = 所有粒子精确重合**(确定性 mode 3 零随机扰动):
    N 个粒子同位置同速度,视觉上仍是 1 个 —— 实测 40000 粒子最大坐标差
    0.000000 Re。已加告警(`plan_status.degenerate_injection` + 日志
    `plan.degenerate_injection` + 前端 toast/HUD),行为不变(要撒多粒子
    请删掉注入节点后**重新应用图**)
26. **画布结构改动必须上传才算数**:增删节点/改连线只在本地点上生效,参数
    才是即时下发。已加「● 画布有未应用修改」角标 + 应用按钮变琥珀色
    (graph.onNodeAdded/onNodeRemoved/onConnectionsChange → 置脏;loadGraph
    与上传成功 → 清脏)。这条踩坑实录:删了注入节点但没上传 → 服务器图里
    注入仍在 → count 调大也"没变化"
27. **仪式性接线审计**(`tests/audit_wiring.py`,对任意图打印"编译出的真相":
    ops 顺序/端口/slots + 渲染绑定):**节点存在 + 参数才是真语义,边只应表示
    数据依赖**。预设实测分类 ——
    - 数据依赖(删了行为就变):`output_slot.out → 积分器.b`
      (→ slots.b=null → **静默无磁场**,无告警)、`output_slot.out →
      场线渲染项.data`(→ 无几何帧)、`output_slot.slot` 参数(引擎
      `declare_output` 自动推导槽位,文件里的 outputs blob 只是可选覆盖)
    - 顺序锚点(非数据依赖但影响谁生效):粒子域 prev/next 链 —— 删掉后计划
      顺序从 `…emitter→step→encode` 变为 `…step→encode→emitter`,而 C++ 侧
      "首个 EmitterOp 生效(v1)"、多 step 按序执行 ⇒ 顺序有语义,却靠链隐式表达
    - 纯装饰(删了什么都不变):渲染域 prev/next 链(前端按**节点类型**实例化,
      绘制 `layer` 写死在渲染项 JS 里 → 连线改不了绘制顺序)、
      `物种.types→发射器.types`、`注入.spec→发射器.init`(活体:删线后注入
      仍生效 n=1 r=6.595)、`输出编码器` 节点(C++ 循环无条件 encode)、
      `render_pipeline_start` 及其 background/fps_cap(**从未被读取**,
      背景写死在 renderer.js,恰好等于其默认值)、`诊断点渲染项`(无 JS 实现)
    → 后续"慢慢改"的方向:① 顺序改成显式参数(渲染 layer / 粒子 order);
    ② 真依赖补诊断(无 B 表告警);③ 装饰项删除或接上;④ 物种表(见 #22 讨论)
28. **顺序显式化(#27 的 ①,已落地)**:**边只表示数据依赖,顺序一律走参数**。
    - 粒子域:各节点新增 `order`(int;默认 发射器 10 / 物种 20 / 注入 25 /
      步进 30 / 编码 40,与历史链序语义一致),`particle_plan()` 按
      `(order, node)` 稳定排序 —— 不再用拓扑序(拓扑序会让"首个 EmitterOp
      生效(v1)"变成隐式副作用)。实测:`pe.order=90` → 发射器排最后;
      `bi.order=5` → 步进排最前
    - 渲染域:各渲染项新增 `layer`(int 0..3,默认 线1/粒子2/标记3),前端
      按 layer 重挂到场景层并设 `renderOrder`(原来是**写死在渲染项 JS** 里,
      连线根本改不了绘制顺序);`render_pipeline_start` 的 background/fps_cap
      **真正接线**(宿主 applyGlobal:背景色 + 帧率上限),不再是死参数
    - **prev/next 端口已从所有粒子/渲染节点规格移除**;旧图里残留的链边由
      `load_json` 容错跳过(记录 `graph.skipped_edges` + 日志 warning),
      严格校验仍留在 `connect()` 给程序化调用 —— 兼容旧文件且不掩盖笔误
    - 迁移:`tests/migrate_graphs.py`(graphs/*.json + 内嵌 C++ 默认图 +
      测试夹具);新增回归 `test_engine_smoke.py::test_explicit_order_and_legacy_edges`
    - 判读工具:`tests/audit_wiring.py` 现在可直接看出"删旧链边零影响""改
      order 即改顺序"
29. **真依赖必须自带诊断(#27 的 ②/③,已落地)**。静默失败是最贵的坑:
    实测"删掉积分器的 b 数据线 → 粒子直线飞行、无任何提示";"删掉场线
    data 线 → 视口空场线、无提示"。现在**编译期诊断随计划上报**:
    - 引擎 `particle_plan()` 返回 `warnings[]`(code/node/port/msg):
      `step_no_b`(步进无 B 表)/ `step_slot_unresolved`(场接在未声明槽位的
      节点上)/ `no_encoder` / `no_emitter`;`render_bindings()` 每条绑定附带
      **解析后的 slot**(服务器据此判 `render_no_slot`,不再各自维护反查表)
    - C++ `Plan.warnings` → `SimPipeline::warnings()`(追加运行期项,如
      degenerate_injection)→ `plan_status.warnings` 广播(**参与变化判定**)
      + 日志 `plan.warning`;**plan_status 也缓存重放**(新连接可见)
    - 前端:toast + HUD「⚠ 计划告警 N 条」+ **画布相关节点红框与原因角标**
      (editor.onPlanWarnings)
    - **编码器节点因此真正生效**:计划无 encode 算子 → 不发送粒子帧(实测
      删除编码器后 5 秒 0 帧);未实现的渲染项(`diagnostics`)在实例化时
      显式告警,并从默认图/预设/内嵌默认图中移除
    - 坑记:JSON `null` 用 `value("slot","")` 会抛 type_error —— 曾把整段
      诊断包在 `catch(...){}` 里静默吞掉,告警全部丢失。判空要用
      `contains() && is_string()`(同 plan_compiler 的 `slot_str`),catch 里
      也必须写日志
30. **粒子种群行表 + 接线决定归属(#27 的 ④,已落地)**。物种是**数据行**,
    不是拓扑:集合语义写在节点上,行序 = 优先级,增删物种不改连线。
    - 新节点 `particle_population`(☰ 粒子种群):`rows` 参数 = 行表
      (preset/name/q/mass/v_mult/weight/color/enabled),新参数类型 **`rows`**
      (engine/ports.py STRUCT_TYPES),属性面板提供**表格编辑器**
      (启用勾选/预设下拉自动回填/名称/q/m/v×/w/色/上移下移/删除/添加行 +
      权重合计与占比提示)
    - `particle_species` 保留为"**1 行种群**"(同一 types 端口类型,可互换)
    - **接线决定归属**(语义修正):发射器 types 接谁就只有谁的物种参与;
      未接线的物种/种群节点**被忽略**并告警 `species_unwired`;仅当 types
      完全未接线时才按图级兜底聚合(告警 `species_not_wired`)。
      注入同理:`init` 未接线 → 注入不生效(告警 `injection_unwired`)。
      → 至此 #27 里"画布在骗人"的最后一类(未接线也生效)被彻底消除
    - C++:`EmitterOp.types_node/init_node`(plan_compiler 解析 emitter 的
      inputs),`set_plan` 只用 init 实际接到的注入算子
    - 迁移:默认图 3 个物种节点 → 1 个种群节点(3 行);测试夹具同步
      (test_ws_species 改用行表,并可整表推送改行内参数)
    - ⚠ 又踩一次 #13:改 `core/plan.h` 后只做增量编译 → 服务器启动即退出
      (退出码 1,无栈);**touch src/*.cpp 全量重编**后正常。头文件改动
      等于全量重编,没有例外
31. **隐式解析摆上画布 + 配套节点随放随补**(用户诉求:"把自动解析的隐式
    节点摆出来,用虚线连接;放置带自解析的就两个一起放")
    - **隐式集合由服务器报告**(`plan_status.implicit`),因为它必须反映
      **引擎真正用到**的东西,而不是前端猜:`emitter`(图内无发射器 → 默认
      发射器)/ `species`(无物种 → 兜底白点)/ `step`·`encoder`(missing=true
      = 图内没有且引擎也不补 → 冻结/不发帧)。注意"只剩场节点"时引擎走
      `make_default_plan`,步进/编码器是**真实存在**的,所以只报 emitter/species
      —— 这正是"按事实摆,不按想象摆"
    - 画布:虚影节点(不可编辑、内写原因)+ **虚线**连到发射器;虚线画在
      `canvas.onDrawForeground`(该回调的 ctx 已在**图坐标**下:LiteGraph 先
      `ds.toCanvasContext` 再画节点)。虚影不入图 JSON、不参与自动布局、
      不计入 HUD(显示 `N 6(+2 隐式)`)
    - **companions**(节点规格字段,`registry.describe` 透出):放置节点时
      递归补齐(深度 2)并按 `wire` 规则连线 —— 放「粒子种群」一次得到
      种群+发射器+积分器+编码器(能跑起来的最小组合);已有同类型节点则复用
    - 时序坑:服务器**重放早于编辑器就绪**(protocol.js 先连 WS)→ 首次加载
      虚影/物种标注/告警红框都不出现。修法:protocol 缓存进 `simStats`,
      editor 就绪时用缓存补齐一次(以后新增这类"事件型消息"都要照此办理)
32. **渲染数据通道契约(#32,兑现"动态渲染插件"的原始意图)**。渲染链当年的
    意图是"从粒子步进管线把标注数据拉到渲染管线",但数据路由从未走链:
    服务器只认场线类的 `data`、前端帧路由按帧头写死、渲染项订阅写死在 JS、
    编码器连输出端口都没有。现在把"拉数据"做成**类型化端口 + 通道声明**:
    - 生产者输出端口:`输出槽.out` = `field_table`(场),**`输出编码器.particles`
      = `particle_buffer`**(新),**`单粒子注入.spec` = `source_spec`**(改)
    - 消费者:渲染项声明 `inputs={"data": Port(<类型>)}` + `channels=[...]`:
      field_lines/efield_lines → `geometry:field_lines|efield_lines`;
      particles/particle_trails → `particles`;
      source_preview/pitch_cone → `source_preview`;diagnostics → `geometry:diagnostics`
    - **接线决定订阅**:`data` 接了才订阅(`renderRegistry.instantiate` 的
      channels 覆盖渲染项自带 subscribes);未接线 = 不渲染 + 服务器告警
      `render_item_unwired`(绑定表带 `channels/needs_data/has_data`)
    - 场线类另有 `render_no_slot`:接了没有输出槽位的节点 → 永不产出几何帧
    - **插件作者契约**(丢文件即生效,无需重启):
      Python 侧 `nodes/render_item_*.py`(domain="render" + data 端口 + channels)
      + JS 侧 `static/renderer/items/*.js`(registerRenderItem)+ index.html 引入。
      完整示例:`nodes/render_item_pitch_cone.py` + `items/pitch_cone.js`
      (以 B̂ 为轴、俯仰角为半顶角画漏斗;已接进单粒子预设)
    - 实测:预设各渲染项订阅 = 接线所得;拔 `enc→rpt.data` 后 `rpt → []`
      (其它项不受影响);新增插件节点热扫即出现在 /api/nodes
35. **持续创生(respawn)+ s 帧信箱合并**(用户:"粒子消失了不会持续创生(悲";
    "给 s 帧做信箱式合并")
    - **持续创生**:死亡粒子(status=1 沉降 / 2 越界)以前**不会重生** ——
      Van Allen 实测 4 秒仿真时间就从 6000 掉到 ~1900 且再也不涨。现在:
      发射器新增 `respawn`(默认 true)→ `particle_plan()` 生成 respawn 算子
      (order 35,但**执行时机由 C++ 固定放在所有步进之后**,与 order 无关)
      → `SimPipeline::step_frame()` 末尾调用既有的 `respawn()`
    - 实测:Van Allen 跑到 t≈234 s 仍 **100% 存活**(修复前 4 s 掉到 31.5%);
      关掉 respawn → 25.4% 并持续衰减,且**两条告警**会说明原因:
      `respawn_off`(编译期)+ `population_decaying`(运行期,死伤过半时,
      由 `refresh_runtime_warnings()` 触发一次性广播)
    - **s 帧信箱合并**:大粒子数时客户端处理不过来,WS 队列积压旧帧 ——
      表现为"服务器早换了图,页面还在放旧粒子数十几秒"(实测服务器 16 fps/
      n=1,页面显示 n=6000 且 t 缓慢推进)。现在 `protocol.js` 对 's' 帧只保留
      **最新一帧**,在 rAF 里消费。实测:服务器 10 秒发 163 帧,页面只
      dispatch 10 次(受页面自身 1 fps 限制)—— 队列积压从结构上不可能
    - ⚠ 踩坑:`has_respawn_` 忘记在 `set_plan` 开头复位 → 旧计划标记残留,
      `respawn_off` 告警判据失效(状态标志必须与 `has_encoder_` 一起复位)
    - ⚠ `plan["count"]` 是**算子个数**不是粒子数(粒子数在发射器算子里),
      新增算子导致多处测试期望值要同步(本次改了 4 处)
36. **偶发静默退出 / 卡死(未结案,已加诊断)**。回归中途服务器两次**静默退出**
    (退出码 1、日志戛然而止、无崩溃记录、无异常文字),复现率约 2/6:
    `tests/test_ws_warnings.py` 触发;A/B 对照(20:44 打的改动前 Release 包)
    通过 1 次、改动后二进制也通过 4 次 → **无法归因,倾向既有偶发问题**
    (崩溃处理器在 8/29 与 9/14 16:08 都记录过访问违例 0xC0000005,同段偏移)。
    **后续又抓到另一种形态:卡死(进程活着但完全不应答)** —— 连 WS 握手都超时、
    keepalive ping 超时,而进程还在。日志证据:停摆前是连续几次 `slots:3` 的
    重烘焙(默认图 T89+尾+对流+屏蔽+大气+重力,coarse,每次几十秒),
    而 Crow 只开 **2 个线程**("using 2 threads")→ 烘焙期间 Python 长期持 GIL,
    HTTP/WS 线程饿死。**下一步专项**:
    ①提高 Crow 线程数(本版 crow.h 无 `multithreaded(N)`,需自行 spawn 或换 API);
    ②烘焙放到独立进程/线程并**真正释放 GIL**(geopack 逐点循环是纯 Python);
    ③上传串行化 + 烘焙看门狗(超时告警而不是静默阻塞);
    ④sim 线程各段加帧号 + try/catch;WER LocalDumps 抓 dump
    已做:`ServerApp::run` 把 `app.run()` 包 try/catch(`run_returned` /
    `run_exception` 进日志),`/MAP` 链接选项本就有(崩溃偏移可符号化)
37. **物理正确性:T89/T96/T01/T04/TS05/TA16 都是"纯外部场"模型**(用户指出
    "T89 似乎是不带偶极子的?"—— 完全正确,而且我此前在预设与指南里写反了)
    - 代码事实:`T89Node.compute` 只调 `geopack.t89.t89(iopt, ps, x, y, z)`;
      GEOPACK 约定 `t89()` 返回**外部磁层场**(磁层顶电流/环电流/磁尾),
      **不含**内部偶极/IGRF —— 总场必须自己加
    - 实测量化(kp=2,赤道面,GSM):

      | r(Re) | T89 外部 | 偶极子 | 相加 | 偶极占比 |
      |---|---|---|---|---|
      | 1.5 | 34 nT | 9244 | 9210 | **100%** |
      | 2.0 | 29 | 3900 | 3871 | **100%** |
      | 4.5 | 6.4 | 342 | 336 | **102%** |
      | 6.6 | 10 | 109 | 119 | 91% |
      | 10 | 32 | 31 | 63 | 49% |

      → **内磁层(r ≲ 6.6 Re)的场几乎全部来自偶极子**;只接 T89 会让场强低
      约 100 倍 —— 画布看着正常、物理全错
    - 影响面:默认图与 `preset_composite_multi` 走 `magnetopause(internal,
      dipole, imf)`,**内部场是加的**(这也是 legacy 位级一致能过的原因);
      而我新写的 `preset_t89_single` / `preset_van_allen` 只接了 T89 → **错**,
      已修成 `T89 + 偶极子 → 加法 → 输出槽`(van_allen 14 节点/11 边、
      t89_single 18 节点/15 边,两者告警清零、实跑 100% 存活)
    - **新增图级诊断 `external_only_field`**(`Graph.field_diagnostics()`,
      并入 `particle_plan()["warnings"]`):从槽位向上游遍历数据依赖图,若链上有
      外部模型(t89/t96/t01/t04/ts05/ta16/tail/imf_source)却**没有**内部场
      (dipole/igrf)→ 结构化告警;`magnetopause` 的 dipole 输入也是一条数据边,
      所以"经磁层顶加偶极"的情形天然不误报(四种组合均已测)
    - 节点名改为「T89 (1989) 外部场」等(T96/T01/T04/TS05/TA16 同样标注),
      docstring 写明"总场 = 本节点 + 内部场";两份指南里的错误说法已改正
      (含把"真实 vs ×0.01"表按**修正后的总场**重算:R_g 0.55 Re / 周期 55 s)
    - `tests/test_presets.py` 的"非 custom 预设零告警"正是这条的守门人
      (补丁前它精确点出那两个预设),另加 `test_external_only_field_diagnostic`

38. **简化面板(左侧 Dock)+ 简化 ⇄ 标准 一键切换**(用户诉求:为预设做简化 UI,
    主体留给地磁场展示,节点动态分类进左侧可收缩 Dock,展开可调参数,加一个与
    标准面板互切的按钮)
    - `static/simple_ui.js` + `#dock`(index.html/CSS):**类别来自节点规格的
      `category`**(磁场/粒子/渲染/输出/组合,未知类别自动兜底 → 新插件不用改
      这里),只列**当前图里真实存在**的节点(换预设即换面板);组内按节点名排序;
      虚影节点(#31)不入面板
    - Dock 可**收缩**(◀/▶,34px 窄条)与刷新(⟳);节点参数**惰性构建**(展开才
      建控件);展开状态与面板模式都记 localStorage
    - **参数控件复用标准面板那一套**:把 `renderProps` 的参数段抽成
      `buildParamsInto(node, container)` 并导出 → Dock 与右侧属性面板对同一节点
      永远一致,改动即时下发(`node.param` → 服务器重编译/重烘焙)
    - 为复用清掉三个坑:①`pop-readout`/`inj-readout` 由**固定 id 改类**(同一节点
      可能同时在两处面板 → id 冲突);②右侧的**内联代码编辑器**只在
      `body.id === "props-body"` 时接管(否则 Dock 会劫持右侧面板);③面板内部的
      "预设回填后重渲染"改为重画**当前容器**而不是右侧面板
    - 工具栏「◧ 简化面板 / ⊞ 标准面板」:简化模式下隐藏画布与右侧属性面板、隐藏
      只对画布有意义的按钮(添加节点/自动布局),3D 视口成为主体(并派发 resize
      让 three.js 重新适配)
    - 实测(CDP):13 节点预设 → 分组 磁场(1)/粒子(5)/渲染(6)/输出(1) ✓;Dock 里
      把偶极子 ps 改成 0.3 → 服务器图 `input_defaults.ps = 0.3` ✓(端到端下发);
      切换:简化(dock=flex/画布 none/属性 none/标签「⊞ 标准面板」)⇄ 标准(画布
      block/属性 block/标签「◧ 简化面板」),localStorage 记 `mf_ui_mode`;收缩:
      300px ⇄ 34px(dock-body 隐藏),localStorage 记 `mf_dock_open`
    - 运维提醒:**后台作业 / `Start-Process` 起的服务器能否跨回合存活不确定**
      (实测:上一回合启的实例活着,再上一轮的没了)→ 让用户自己启动最稳
      (`scripts\start.bat`),或用任务计划程序建一次性任务(脱离作业对象)

39b. **A2000 抛物面模型节点(偶极子的升级版)**。用户提议用 Toffoletto–Hill 作偶极子
    升级;调研后改选**抛物面模型(CPMOD/A2000 家族)**——它的卖点正合我们的架构:
    磁场写成**电流源叠加**(偶极 + 环电流 + 尾电流 + 磁层顶 CF 屏蔽×2 + Region-1 FAC
    + 穿透 IMF),Dst 驱动环电流、AL 驱动尾瓣磁通、太阳风动压+IMF Bz 定 R1/FAC
    - 源码:**IRBEM 的标准双精度实现**(`models/a2000_irbem.f`;SpacePy 本机自带,
      另有作者组官网 magnetosphere.ru 与 PRBEM/IRBEM 仓库)。第一版误用竞赛项目的
      `models/parabmod.for`(bimf 隐式标量 → 靠 -fallow-argument-mismatch 硬编),
      结果是**总场尚可、Dst 完全无响应**(环电流行恒 7.7 nT)—— 典型的"画布正常物理全错"
    - 编译:`scripts/build_a2000.ps1`(需 64 位 gfortran;PATH 里的 mingw32 是 32 位,
      配不了 64 位 Python)。f2py 2.x 在 Python≥3.12 走 meson 且包装 Bessel 例程时崩
      (KeyError besj0)→ 改为**普通 DLL + ctypes**(不绑 Python 版本,便携包只多
      1 个 dll + 4 个 gfortran 运行库)
    - `models/a2000_api.f90`:**两段式**包装 —— `submod()` 由空间天气算 par(1..10)
      每图一次,`A_field()` 逐点求场(这正是模型自己的结构,比每点重算快一个量级);
      时间走模型的 `COMMON /a2000_time/`;带 `ifail`;`PRINT` 刷屏用 fd 级静音屏蔽
    - 验收(`tests/test_paraboloid_model.py`,5 项全过):①**参数映射与作者组在线工具
      earth3d 逐项吻合**(R1 10.411 vs 10.436、R2 7.287 vs 7.305、BR −10、AJ0 0.580、
      Φ∞ 472.6 vs 472.998 MWb、B0 −29554 vs −29644 nT);②总场与解析偶极量级一致;
      ③**Dst 0→−50→−150 赤道 r=2 Re 总场 3691→3653→3611 nT 单调下降**(环电流真生效);
      ④Ox 轴格点有限;⑤tiny 114k 点求值 **1.24 s**
    - 已知限制/待办:①抛物面坐标在 **Ox 轴奇异**(源码警告,实测 NaN)→ 节点把 ρ<0.02 的
      格点沿 y 轻推 0.02 Re;②模型给的 7 个**分源行**在该 IRBEM 变体里量级对不上、
      `PSTATUS` 开关对总场无影响(疑似内部 bd0/bka 归一化)→ **只输出总场**,分源/开关
      留 TODO;③本模型已含尾电流与磁层顶电流,与 T89 相加会重复计 → 推荐单独使用
      或只叠均匀 IMF;④`_INTERNAL_FIELD_MODELS` 已加入 paraboloid(自带偶极,
      不会误报 external_only_field)
33. **引导页 + 预设自动发现**(用户诉求:"打开网页看到仿真标题与几个预设
    各自的选项框(自动排列,方便工程内添加),保留一个『自定义』入口进入
    标准空预设")
    - 服务器:`GET /api/presets` 扫 `graphs/preset_*.json` → 卡片列表
      (id/name/desc/custom/sort/lattice/nodes/edges);`GET /api/preset?id=xx`
      取图 JSON(仅允许 `preset_<id>.json`,字符白名单防目录穿越)
    - 预设文件可带 **meta 块** `{"preset": {...}}`(引擎/编辑器忽略未知顶层
      键,安全);缺省用文件名。**加预设 = 放一个 preset_*.json**(+ 可选 .md),
      引导页自动多一张卡片,不用改任何代码 —— 卡片用 CSS grid `auto-fill`
      自动排列
    - 前端 `static/launcher.js` + `#launcher` 覆盖层:标题 / 副标题 / 卡片网格
      / 「跳过,保持服务器当前的图」;卡片点击 = `loadGraph(doc)` +
      `uploadGraph(doc)`;`localStorage.mf_last_preset` 记住上次(高亮 + 「上次」
      角标);工具栏「☰ 预设」随时重新打开
    - `graphs/preset_custom_empty.json` = 自定义入口(空画布、点阵 coarse,
      meta.custom=true → 虚线卡片)
    - 新增 `tests/test_presets.py`:跟着发现列表走 —— 卡片字段齐全、必须有
      custom 入口、每个预设的图能加载、**非 custom 预设零告警**(计划/绑定/
      slow_path/B 槽位),即"出厂预设不许带病"
34. **三个演示预设 + 预设健壮性修复**(用户:Van Allen 用现成球面随机发生器即可,
   不必新增播种节点)。新增 `preset_t89_single` / `preset_composite_multi` /
    `preset_van_allen`(各带 .md 指南与 meta 卡片),实测烘焙/帧数:
    - `t89_single`(16 节点/12 边,烘焙 5.5 s):T89(kp=2)→ `mul(w=0.01)` 缩放场
      → 单粒子;**回旋半径 0.005 Re → 0.5 Re** 可见螺旋,substeps=50;
      配俯仰角锥插件读初条件
    - `composite_multi`(17 节点/19 边,烘焙 5.6 s):T89 + tail(harris)+ 倾斜偶极
      + IMF 经 `magnetopause(mp_model=2)` 合成;种群表 电子/质子/α 权重 2:2:1
      (实测前 400 个粒子 128/116/56);emitter mode=1 球面 r=8 撒 3000
    - `van_allen`(10 节点/6 边,烘焙 0.1 s):偶极 + **球面随机发生器**
      (mode=1, r=4.5 Re, 4000 粒子)→ 赤道附近俯仰角≈90° 磁镜捕获成带;
      拖尾关闭保帧率。实测画面为蓝红球壳带
    - **发现并修掉一个真 bug**:`Node` 实例参数**不合并规格默认值**,而节点代码
      普遍是 `self.params["x"]` 直接索引 → 手写图只写关心的字段就 KeyError
      (`imf_source` 的 `parker_custom`)。这类图**服务器 bake 报 error**,而
      只编译计划看不出来。修法:`Graph.add_node` 构造后按规格 `setdefault` 补齐
      (仅填缺失);`tests/test_presets.py` 增加"**必须真的烘焙一遍**"检查
      —— 就是它漏掉的那一步
    - 运维提醒:引擎 Python 模块只在**服务器启动时**导入(`nodes/*.py` 才热扫),
      改 `engine/*.py` 后必须重启服务器(本轮踩到:测试用新引擎通过、服务器仍报旧错)
