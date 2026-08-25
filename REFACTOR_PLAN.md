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

### 5.7 执行计划(粒子域子图)

```cpp
struct PlanOp {
    OpKind kind;                  // 原生算子 id
    std::vector<BufferRef> in, out;
    ParamSnapshot params;         // 参数更新 = 换快照,不重建计划
    // 或 PyOp: Python 节点 → GIL + numpy 零拷贝视图
};
struct Plan { std::vector<PlanOp> ops; bool slow_path; };
```

- 编辑期:拓扑排序 → 计划描述 JSON → `plan.install()`;
  运行时 sim 线程顺序执行,**全原生 = 每帧零 Python**
- 含 Python 节点的混合计划打 `slow_path` 标记 → 前端成本徽标 + 建议粒子数上限

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

## 10. 已确认与待办

**已确认**:输出槽位自由声明(D10)、架构分工(D2)、Field 点阵重构(D7)、
原生模块插件化与槽位替换(D8/D9)。

**后续可扩展**(不在首期):.pyd 原生插件 SDK(用户编译原生内核)、
跨机器图分发、Reduce/Stat 等高级组合节点、辐射带/其他场模型新插件。
