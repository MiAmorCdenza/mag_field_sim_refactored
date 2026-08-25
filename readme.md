# 地球磁场与带电粒子运动实时仿真器 (EarthMagFieldSim)

基于 C++ (Crow + 嵌入式 Python) 和前端 WebGL (Three.js) 的空间物理实时仿真项目。通过求解相对论洛伦兹力方程，在浏览器中以极高帧率实时模拟带电粒子在真实地球磁场中的三维动力学行为。

## 架构

```
浏览器 (Three.js/WebGL)  ←WebSocket→  C++ Crow 服务器  ←嵌入式Python→  T89/T96/T01 网格 + NOAA Kp
         ↑                                        ↑
    static/                                   physics_engine.cpp
  (index.html                              (Boris相对论积分器
   main.js)                                  多线程并行)
```

- **后端**：纯 C++ Crow HTTP/WebSocket 服务器，内嵌 Python 解释器仅用于 T89/T96/T01 磁场网格计算和 NOAA Kp 指数拉取
- **物理引擎**：就地编译为单个可执行文件，Boris 相对论积分器 + 多线程并行步进（每个物理步长 2 万粒子亚毫秒级处理）
- **前端**：Three.js InstancedMesh + LineSegments，20000 粒子仅 2 次 Draw Call

## 快速开始

### 编译

```powershell
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

生成 `build/Release/MagFieldSim_Server.exe`（~600 KB）。

### 运行

```powershell
.\build\Release\MagFieldSim_Server.exe
```

浏览器打开 `http://localhost:8001`。

首次启动计算 T89 网格（61×41×41 = 10.2 万采样点）约需 30 秒，之后再启动秒开。

### 部署到其他电脑

```powershell
.\deploy.ps1    # 生成 deploy_package/EarthMagFieldSim.zip
```

目标电脑需安装 Python 3.10+ 和 VC++ Redistributable x64。双击 `run.bat` 启动，自动安装 `numpy geopack requests`。

## 核心特性

### 磁场模型

| 模型 | 说明 |
|------|------|
| **简易解析模型** | 倾斜偶极子 + 镜像偶极子（磁层顶压缩）+ 磁尾拉伸 |
| **T89** (默认) | 外部磁场，仅需 Kp 指数 |
| **T96** | 包含磁层顶 + 磁尾 + 环电流，参数更丰富 |
| **T01** | 最新模型，支持暴时动力学 |

Kp 指数可手动控制或勾选自动更新（每 5 分钟从 NOAA 拉取）。太阳风压缩系数与 Kp 联动：`compression = 1.0 + Kp/9.0`。

### 物理模型

- 相对论 Boris 积分器（自适应亚步长，最多 20 亚步）
- 晨昏对流电场 + 地球自转共转电场 + Volland-Stern 屏蔽模型
- 热层大气阻尼（单层指数 / 分层模型）
- 地球引力场
- 多种粒子类型：质子 (m=1.0 amu)、电子 (m=0.00054 amu)、α 粒子 (He²⁺, m=4.0 amu)
- 三种发射器模式：定向盘面 / 全向球面 / 体积随机

### 可视化

- 粒子数 > 5000 建议关闭拖尾以保证帧率
- 渲染半径可独立调节（视野外粒子静默计算、节省 GPU）
- 碰撞轨迹永久渲染
- 磁场线实时绘制

## 实验指南

### 实验 1：范艾伦辐射带 (Van Allen Belts)

- **模型**：T89，Kp=2
- **粒子类型**：质子 + 电子 + α 粒子
- **发射器**：球面发射或体积随机
- **现象**：粒子在偶极场中的三重运动——回旋、弹跳、漂移。质子→西漂，电子→东漂，形成环电流。

### 实验 2：磁镜效应 (Magnetic Mirroring)

- **粒子数**：1000
- **发射器**：全向球面发射，增大角度随机量
- **现象**：粒子向极区俯冲时被强磁场反弹，仅极小投掷角粒子落入损失锥。

### 实验 3：阿尔芬层不对称性

- **电场**：启用，选择 Volland-Stern 屏蔽模型，倍率 5.0x
- **现象**：E×B 漂移使质子沉降在晨侧，电子沉降在昏侧。

### 实验 4：大气阻尼与极光沉降

- **大气**：启用分层模型，倍率 10.0x
- **现象**：粒子在热层中减速、螺旋、沉降，留下弹簧状永久轨迹。

### 实验 5：磁层拓扑

- **模型**：T96 或 T01
- **现象**：磁力线不再对称——日侧压缩变扁，夜侧拉伸为彗星状磁尾。

## 文件结构

```
mag_field_sim/
├── MagFieldSim_Server.exe   # 编译产物
├── physics_engine.cpp        # 物理引擎（Boris、磁场、粒子管理）
├── server_main.cpp            # Crow 服务器入口 + WebSocket 处理
├── python_bridge.py           # T89/T96/T01 网格计算 + NOAA Kp 拉取
├── config.json                # 默认仿真参数
├── CMakeLists.txt             # 构建配置
├── deploy.ps1                 # 一键打包脚本
├── run.bat                    # 目标电脑启动器
├── static/
│   ├── index.html
│   └── main.js
└── README.md
```
