# 地球磁场与带电粒子运动实时仿真器 (EarthMagFieldSim)

**节点式**空间物理仿真平台:把「场模型 → 粒子推进 → 可视化」拆成可插拔节点,
在浏览器里实时看三维结果。C++ 原生热路径(Crow + 嵌入式 Python 只做烘焙),
前端 Three.js 由**浏览器端 JS 渲染插件**驱动。

> 当前版本 **v0.2.1-beta**(初步测试版)。反馈请附 `logs\server.jsonl` 末尾几行。

## 快速开始(便携包,推荐发给别人测试)

1. 解压 zip 到任意目录(路径别太深)
2. 双击 **`启动.bat`** —— 自动启动服务器并打开浏览器 `http://127.0.0.1:8001`
3. 首屏是**引导页**:选一个预设开始,或进「自定义 / 空预设」搭自己的图

要求:Windows 10/11 x64。**无需安装 Python / VS / VC 运行库**(嵌入式
Python 3.14 与 numpy/geopack、CRT 都在包里)。停止:任务管理器结束
`mf_server.exe`,或 `Get-Process mf_server | Stop-Process`。

## 预设(引导页里各一张卡片)

| 卡片 | 看什么 |
|---|---|
| **标准偶极子 · 单粒子** | 单粒子工具:确定性初条件、磁镜捕获、初条件预览 + 俯仰角锥 |
| **T89 磁层 · 单粒子** | T89 场线拓扑 + `mul(w=0.01)` 缩放场后的可见回旋螺旋 |
| **复合场 · 多种群** | T89 + 磁尾 + 偶极 + IMF 经磁层顶合成;电子/质子/α 三种群 |
| **Van Allen 辐射带(T89)** | 体积随机播种 + c/3 动能 → 损失锥沉降、其余磁镜捕获成带 |
| **自定义 / 空预设** | 空白画布,从零搭图 |

每个预设都配一份同名 `.md` 调试指南(图结构、参数速查、物理预期、已知取舍)。

## 架构(三域节点图)

```
场域(Python 烘焙)          粒子域(C++ 原生,每帧零 Python)      渲染域(浏览器 JS)
偶极/T89/T96/… → 输出槽 ──┬─→ Boris/蛙跳/RK4/Verlet ─→ 编码器 ──┬─→ 场线/粒子/拖尾/…
                          └─→ 场线渲染项(服务器追踪)            └─→ 初条件预览/俯仰角锥/…
```

- **场域**:节点声明式,`evaluate()` 拉取式求值 + 内容寻址缓存,结果烘焙成
  三线性查表(`Table3D`)交给 C++
- **粒子域**:`Graph.particle_plan()` 把子图编译成执行计划(POD JSON),
  `SimPipeline` 按计划跑原生内核;`IBatchAdvancer` 是可插拔内核 seam,
  4 个内置内核(Boris 与老引擎位级一致 / 蛙跳 / RK4 / Verlet)
- **渲染域**:**接线决定订阅** —— 数据通道按端口类型路由(`field_table` →
  `geometry:*` 帧、`particle_buffer` → `particles` 帧、`source_spec` →
  `source_preview` 消息);拔掉数据线该渲染项就不订阅,服务器同时告警

### 两条贯穿设计

1. **边只表示数据依赖,顺序走参数**:粒子域有 `order`,渲染域有 `layer`
   (早期版本靠 `prev/next` 链表达顺序与成员关系,已移除)
2. **画布必须说真话**:引擎隐式用到的东西会以**虚影节点 + 虚线**摆在画布上
   (默认发射器 / 兜底物种 / 缺积分器=冻结 / 缺编码器=不发帧);编译期诊断
   (无 B 表、槽位未解析、渲染项未接线、注入+count>1 退化…)经
   `plan_status.warnings` 报到界面(toast + HUD + 节点红框)

## 插件(丢文件即生效,无需重启)

- **场/粒子域节点**:放一个 `nodes/*.py`(声明式),registry 热扫即出现在「添加节点」
- **渲染项**:`nodes/render_item_*.py`(声明 `data` 端口类型 + `channels`)
  \+ `static/renderer/items/*.js`(`registerRenderItem`)+ `index.html` 引一行;
  数据端口接上才订阅。完整示例见
  `nodes/render_item_pitch_cone.py` + `static/renderer/items/pitch_cone.js`

## 开发环境

```powershell
scripts\start.ps1          # 建 .venv、装依赖、编译、起服务器(开发用)
scripts\check_env.ps1      # 环境自检
scripts\package.ps1 -Version v0.2.0-beta   # 打便携包 → dist\*.zip
```

服务器参数:`mf_server.exe --root . --port 8001 --particles 20000 [--graph graphs\preset_x.json]`

## 测试

```powershell
# 引擎与预设(纯 Python / 需服务端)
.\.venv\Scripts\python.exe tests\test_engine_smoke.py     # 引擎冒烟(计划/通道/行表/诊断)
.\.venv\Scripts\python.exe tests\test_field_nodes.py      # 场节点 vs 旧引擎(19 诊断点,位级一致)
.\.venv\Scripts\python.exe tests\test_presets.py          # 预设完整性(含真烘焙,零告警)
.\.venv\Scripts\python.exe tests\test_preset_single.py    # 单粒子预设端到端
.\.venv\Scripts\python.exe tests\test_ws_warnings.py      # 计划诊断端到端
.\.venv\Scripts\python.exe tests\test_ws_client.py        # WS 协议端到端
.\.venv\Scripts\python.exe tests\audit_wiring.py          # 接线审计(哪些边是真依赖)

# C++ 侧(独立编译)
server\build\headless.exe    # 能量守恒 / 2 万粒子性能 / 编码协议 / 注入语义
server\build\tracer_test.exe # 磁力线追踪器验收
```

## 端口与文件

- 网页 `http://127.0.0.1:8001`;WS `ws://127.0.0.1:8001/ws`
- 日志(单一 JSON 流):`logs\server.jsonl`(含前端 warn 以上)
- 图与预设:`graphs\`(放 `preset_*.json` 即自动出现在引导页)
- 点阵预设:`tiny`(快,开发/预设用)/ `coarse`(legacy 视场)/ `fine`

## 已知限制(v0.2.1-beta)

- 一个图上只有**第一个发射器**生效(v1);多发射器在路线图上
- 电子回旋周期 ~1e-4 s,在 `dt=0.01` 下欠采样(弹跳/漂移仍正确)
- `tiny` 点阵外层格距 ~1 Re,定量结论建议用 `coarse` 复核
- Windows x64 专用;Linux/macOS 未打包
- 重图(默认图 coarse,T89+尾+对流+屏蔽+大气+重力)烘焙一次几十秒,期间页面可能
  短暂无响应(已知问题,见 REFACTOR_PLAN #36);轻量预设不受影响

## 验收基线

默认图烘焙与老引擎在 19 个诊断点上**位级一致**(`test_field_nodes.py`,
`max|Δ|=0.00e+00`);2 万粒子单步 < 5 ms 预算(实测 ~0.23 ms/步)。
