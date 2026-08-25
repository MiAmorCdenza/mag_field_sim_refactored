# SWMF 源代码分析报告 — Windows 可移植性

> **分析日期:** 2026-07-23  
> **原始代码位置:** `/home/kosaka/mag_field_sim/external/SWMF`  
> **目标:** 重建目录树以支持 Windows 平台编译  
> **原则:** 不动原始代码，在新目录 `/home/kosaka/SWMF_Cross_Platform` 中构建

---

## 1. 项目概述

SWMF (Space Weather Modeling Framework) 是由密歇根大学开发的空间天气建模框架。它通过耦合多个物理组件来模拟从太阳到地球电离层的空间等离子体环境。

- **语言:** Fortran 90/95 (约500+ .f90源文件) + C/C++ (约20+ 文件) + Perl构建脚本
- **并行:** MPI / OpenMP / OpenACC (GPU)
- **构建系统:** GNU Make + Perl 配置脚本
- **编译器支持:** nvfortran, gfortran, ifort/ifx, nagfor, flang, xlf90, crayftn
- **操作系统:** Linux (17种编译器配置), macOS/Darwin (8种编译器配置), **不支持Windows**

---

## 2. 目录树结构

```
SWMF/                                   # 根目录
├── Config.pl                           # 主配置脚本 (Perl)
├── Makefile                            # 顶层Makefile
├── Makefile.conf                       # 编译器配置 (nvfortran)
├── Makefile.def                        # 组件版本定义
├── Makefile.test                       # 测试Makefile
│
├── CON/                                # 控制层 (Control infrastructure)
│   ├── Makefile
│   ├── Makefile.def
│   ├── Control/src/                    # 主程序 swmf.f90 + 控制逻辑
│   │   ├── Makefile
│   │   ├── Makefile.RULES.all
│   │   ├── swmf.f90                    # PROGRAM swmf (主入口)
│   │   ├── swmf_interface.f90          # C/Fortran 外部API
│   │   ├── CON_main.f90                # Module CON_main (initialize/finalize)
│   │   ├── CON_session.f90             # Module CON_session (init_session/do_session)
│   │   ├── CON_io.f90                  # Module CON_io (read_inputs/save_restart)
│   │   └── CON_variables.f90           # Module CON_variables (全局变量)
│   ├── Library/src/                    # 基础库
│   │   ├── CON_comp_param.f90          # 组件名与参数定义
│   │   ├── CON_comp_info.f90           # 组件信息类型
│   │   ├── CON_physics.f90             # 物理常量与坐标
│   │   ├── CON_time.f90                # 时间管理
│   │   └── CON_world.f90               # MPI世界管理 (进程/线程)
│   ├── Coupler/src/                    # 耦合框架工具包
│   │   ├── CON_coupler.f90             # 耦合主控
│   │   ├── CON_router.f90              # 网格路由
│   │   ├── CON_grid_descriptor.f90     # 网格描述符
│   │   ├── CON_grid_storage.f90        # 网格存储
│   │   ├── CON_domain_decomposition.f90 # 域分解
│   │   ├── CON_global_message_pass.f90 # 全局消息传递
│   │   ├── CON_transfer_data.f90       # 数据传输
│   │   ├── CON_couple_points.f90       # 点耦合
│   │   └── CON_bline.f90              # 磁力线耦合
│   ├── Interface/src/                  # 22个组件间耦合器
│   │   ├── CON_wrapper.f90             # 组件包装器
│   │   ├── CON_couple_all.f90          # 统一耦合入口
│   │   └── CON_couple_XX_YY.f90 (x22)  # 各组件对耦合器
│   └── Stubs/src/                      # 桩实现
│       ├── CON_wrapper.f90
│       └── CON_couple_all.f90
│
├── GM/                                 # Global Magnetosphere (磁层)
│   ├── Empty/src/GM_wrapper.f90        # 空实现 (CON_stop)
│   └── BATSRUS/src/                    # 完整BATSRUS物理模型 (~70 .f90)
│       ├── ModAdvance.f90
│       ├── ModPhysics.f90
│       ├── ModEquation*.f90 (35+)
│       ├── ModUser*.f90 (20+)
│       └── srcInterface/GM_wrapper.f90
│
├── IE/                                 # Ionospheric Electrodynamics (电离层电动力学)
│   ├── Empty/src/IE_wrapper.f90
│   └── Ridley_serial/
│
├── IH/                                 # Inner Heliosphere (内日球层)
│   ├── Empty/src/IH_wrapper.f90
│   └── BATSRUS/srcInterface/IH_wrapper.f90
│
├── IM/                                 # Inner Magnetosphere (内磁层)
│   ├── Empty/src/IM_wrapper.f90
│   ├── CIMI/
│   ├── HEIDI/
│   └── RCM2/
│
├── EE/                                 # Eruptive Event (爆发事件)
│   ├── Empty/
│   └── BATSRUS/srcInterface/EE_wrapper.f90
│
├── OH/                                 # Outer Heliosphere (外日球层)
│   ├── Empty/src/OH_wrapper.f90
│   └── BATSRUS/
│
├── SC/                                 # Solar Corona (日冕)
│   ├── Empty/src/SC_wrapper.f90
│   └── BATSRUS/
│
├── PC/                                 # Particle Code (粒子代码)
│   ├── Empty/src/PC_wrapper.f90
│   └── FLEKS/
│
├── PS/                                 # Plasmasphere (等离子体层)
│   └── Empty/src/PS_wrapper.f90
│
├── PT/                                 # Particle Tracker (粒子追踪)
│   ├── Empty/src/PT_wrapper.f90
│   ├── AMPs/
│   └── MITTENS/
│
├── PW/                                 # Polar Wind (极风)
│   ├── Empty/src/PW_wrapper.f90
│   └── PWOM/
│
├── RB/                                 # Radiation Belt (辐射带)
│   ├── Empty/src/RB_wrapper.f90
│   └── RBE/
│
├── SP/                                 # Solar Particles (太阳粒子)
│   ├── Empty/src/SP_wrapper.f90
│   └── MFLAMPA/
│
├── UA/                                 # Upper Atmosphere (高层大气)
│   ├── Empty/src/UA_wrapper.f90
│   └── MGITM/
│
├── CZ/                                 # (很少使用)
│   └── Empty/
│
├── share/                              # 共享代码
│   ├── Library/src/                    # 共享基础库 (~30 .f90)
│   │   ├── ModMpi.f90                  # MPI接口
│   │   ├── ModKind.f90                 # 精度定义
│   │   ├── ModConst.f90                # 物理常量
│   │   ├── ModNumConst.f90             # 数值常量
│   │   ├── ModUtilities.f90            # 工具函数
│   │   ├── ModReadParam.f90            # 参数读取
│   │   ├── ModFreq.f90                 # 频率/时间控制
│   │   ├── ModTimeConvert.f90          # 时间转换
│   │   ├── ModCoordTransform.f90       # 坐标变换
│   │   ├── ModInterpolate.f90          # 插值
│   │   ├── ModIoUnit.f90               # IO单元管理
│   │   ├── ModSort.f90                 # 排序
│   │   ├── CON_axes.f90                # 坐标系
│   │   ├── CON_planet.f90              # 行星参数
│   │   ├── CON_planet_field.f90        # 行星磁场
│   │   ├── CON_geopack.f90             # 地磁坐标
│   │   ├── MOD_*.f90 (若干)
│   │   └── *.cpp/*.h (C/C++支持)
│   ├── build/                          # 编译器配置 (40+ Makefile)
│   └── Scripts/                        # 大量 Perl 脚本
│
├── util/                               # 工具库
│   ├── NOMPI/src/                      # 无MPI模拟层
│   ├── TIMING/src/                     # 性能计时
│   ├── DATAREAD/                       # 数据读取
│   ├── EMPIRICAL/                      # 经验模型
│   ├── CRASH/src/                      # 辐射冲击 (30+ .f90)
│   └── FISHPAK/src/                    # FISHPAK 泊松求解器 (.f)
│
├── ESMF/ESMF_SWMF/                     # ESMF耦合接口
│   ├── src/ (7 .f90)
│   └── input/ (.yaml, .inp)
│
├── Param/                              # 输入参数文件
├── Scripts/                            # 脚本
├── doc/                                # 文档
└── Copyrights/                         # 版权
```

---

## 3. 构建系统架构

### 3.1 构建流程

```
Config.pl 启动
  │
  ├─ git clone (按需获取组件仓库)
  ├─ 生成 Makefile.def (组件版本选择)
  ├─ 生成 Makefile.conf (从 share/build 复制对应OS/编译器的模板)
  ├─ 生成 Makefile (从 CMP 配置文件处理)
  └─ 生成 Makefile.RULES (从 Makefile.RULES.all 生成)

make SWMF
  │
  ├─ include Makefile.def  →  设定组件路径
  ├─ include Makefile.conf →  编译器设置
  ├─ cd CON/Control/src; make LIB
  │   ├─ 递归编译所有依赖库:
  │   │   share/Library/src/  → libSHARE.a
  │   │   util/*/src/         → libTIMING.a, libINDICES.a, ...
  │   │   CON/Library/        → libLIBRARY.a
  │   │   CON/Coupler/        → libCOUPLER.a
  │   │   GM/IE/IH/.../       → libGM.a, libIE.a, ...
  │   │   CON/Interface/      → libINTERFACE.a
  │   └── CON/Control/        → libCONTROL.a
  └─ link → bin/SWMF.exe
```

### 3.2 编译配置模板 (share/build/)

每个模板命名格式: `Makefile.${OS}.${COMPILER}`

| OS     | 编译器数 | 示例 |
|--------|---------|------|
| Linux  | 17      | gfortran, nvfortran, ifort, ifx, nagfor, crayftn... |
| Darwin | 8       | gfortran, nvfortran, ifort, nagfor, flang, xlf90... |

**关键: 没有 `Makefile.Windows.*` 模板**

### 3.3 配置脚本 Share/Scripts/Config.pl

OS 检测逻辑 (第12-24行):

```perl
# 默认编译器映射
$DefaultCompiler = 'gfortran'  if $OS eq 'Linux';
$DefaultCompiler = 'nagfor'    if $OS eq 'Darwin';
$DefaultCompiler = 'gfortran'  if $OS eq 'Cygwin';  # 已有Cygwin支持!
# 但未定义 Windows 平台的 OS 名称
```

C编译器映射:
```perl
$DefaultCompilerC = 'gcc_mpicc'  if $OS eq 'Linux';
$DefaultCompilerC = 'clang_mpicc' if $OS eq 'Darwin';
$DefaultCompilerC = 'gcc_mpicc'  if $OS eq 'Cygwin';
```

---

## 4. 组件接口规范

### 4.1 标准 Wrapper 接口

每个物理组件都实现统一个模块 `XX_wrapper`，包含5个必须的 public subroutine:

```fortran
module XX_wrapper
  use ModUtilities, ONLY: CON_stop
  implicit none
public :: XX_set_param      ! 设置参数
public :: XX_init_session   ! 初始化会话
public :: XX_run            ! 执行计算
public :: XX_save_restart   ! 保存断点
public :: XX_finalize       ! 收尾清理
```

### 4.2 组件分类

| 类型 | 组件 | wrapper实现 |
|------|------|------------|
| **MHD网格类** | GM, IH, OH, SC | 使用GridType/LocalGridType，支持空间耦合 |
| **简单类**    | IE, IM, PS, PW, RB, UA, SP, PT, PC | 基础wrapper，无网格类型 |

### 4.3 组件模块依赖图

```
                          swmf.f90 (主程序)
                              │
                         CON_main (初始化/清理)
                              │
                       CON_session (会话管理)
                         /    │    \
              CON_io      CON_coupler   CON_wrapper
         (输入/输出)    (耦合控制)    (组件包装)
              │              │            │
         CON_time      CON_router   GM_wrapper/IE_wrapper/...
         CON_physics   CON_grid_*        │
         CON_axes      CON_bline    ModMpi, ModUtilities
                        │
              ┌─────────┴──────────────────┐
         share基础层                  组件层 (GM,IE,IM,...)
         ModMpi, ModKind,            各自Mod*模块
         ModConst, ModUtilities,
         ModReadParam, ModIoUnit
```

---

## 5. Windows 可移植性问题分析

### 5.1 致命问题 (必须解决)

| # | 问题 | 位置 | 严重性 |
|---|------|------|--------|
| 1 | `SHELL=/bin/sh` | **所有 120+ Makefile** | 致命 |
| 2 | 无 `Makefile.Windows.*` 模板 | `share/build/` | 致命 |
| 3 | Perl shebang `#!/usr/bin/perl` + `#!/bin/sh` | `Config.pl`, `Configure.pl` | 致命 |
| 4 | `uname` 命令检测OS | `share/Scripts/Config.pl` 和 `Config.pl` | 致命 |
| 5 | `hostname -f` 命令 | `share/Scripts/Config.pl` | 致命 |
| 6 | Unix `cp`, `mv`, `ln -s`, `rm -rf` 等命令 | 多处 Makefile | 致命 |
| 7 | `ls -d [A-Z][A-Z]/*/` shell glob | 顶层 Makefile | 致命 |
| 8 | `ar -rs` 归档工具 | `Makefile.conf` | 致命(需ar) |
| 9 | `${MPIRUN}` 默认为 `mpiexec` | Makefile.def | 关键 |
| 10 | Fortran模块搜索 `-I${INCLDIR}` | 通用 Makefile.conf | 关键 |

### 5.2 编译器/库问题

| # | 问题 | 当前设置 | Windows替代 |
|---|------|---------|-------------|
| 11 | 当前配置 nvfortran | nvhpc | 需要 MinGW/gfortran 或 Intel Fortran for Windows |
| 12 | 双精度标志 `-r8` | nvfortran | Windows: gfortran `-fdefault-real-8`, Intel `/real_size:64` |
| 13 | 模块输出 `-module ${INCLDIR}` | nvfortran | gfortran: `-J`, Intel: `/module:` |
| 14 | 预处理 `-Mpreprocess` | nvfortran | gfortran: `-cpp`, Intel: `/fpp` |
| 15 | OpenACC `-acc -gpu=cc120` | nvfortran | Windows无NVIDIA Fortran OpenACC |
| 16 | MPI库路径 | MPICH/OpenMPI | MS-MPI 或 MinGW-MPICH |
| 17 | BLAS/LAPACK | 空(自带) | Windows需配置路径 |

### 5.3 运行时问题

| # | 问题 | 分析 |
|---|------|------|
| 18 | Fortran `OPEN(NEWUNIT=...)` 是F2008特性 | gfortran >= 4.9 支持 |
| 19 | `SYSTEM` 调用 | 代码中可能有 `CALL SYSTEM("bash cmd")` 调用 |
| 20 | 文件路径分隔符 `/` vs `\` | Fortran中 `/` 通常能工作，但要确认 |
| 21 | 动态库 `.so` vs `.dll` | 当前全部静态库 `.a`，暂无问题 |
| 22 | `.f90` vs `.F90` 文件名大小写 | Windows 不区分大小写，可能冲突 |

### 5.4 构建系统流程问题

| # | 问题 | 详情 |
|---|------|------|
| 23 | `Config.pl -install` 调用 `git clone` | Windows上需要 Git for Windows |
| 24 | Perl 内 `chdir`, `system()`, glob 依赖 Unix 路径 | 需要仔细审计 |
| 25 | `make dist` 使用 `tar` | Windows 没有原生 tar |
| 26 | `make rundir` 使用 `ln -s` 创建符号链接 | Windows 有 mklink 但权限要求高 |
| 27 | `make tags` 使用 `etags` | 仅限 Emacs |

### 5.5 C/C++ 混合编译问题

| # | 问题 | 详情 |
|---|------|------|
| 28 | `share/Library/src/*.cpp` 需要 C++ 编译器 | Windows 上 MinGW g++ 或 MSVC |
| 29 | `share/Library/src/*.h` C 头文件 | 需要确保与 Fortran ISO_C_BINDING 兼容 |
| 30 | `LINK.cpp = ${COMPILE.c} -lstdc++` | Windows 链接方式不同 |

### 5.6 注释标记 `^CMP` 系统

整个代码库使用 `^CMP` 标记系统进行条件编译配置，由 `Configure.pl` (Perl脚本) 处理。所有 `.f90`, `Makefile`, `.options` 文件中包含如下指令:

```
!^CMP IF GM BEGIN
...code...
!^CMP END GM
```

这套系统依赖 Perl + Unix 路径，在 Windows 上需要相应调整。

---

## 6. 重建方案设计

### 6.1 总体策略: CMake 构建系统

**选择 CMake 的理由:**
- 跨平台原生支持 (Windows/Linux/macOS)
- 原生 Fortran 支持 (`enable_language(Fortran)`)
- 内置 MPI 发现 (`find_package(MPI)`)
- 支持 HDF5, BLAS/LAPACK 等库查找
- 生成 Visual Studio / NMake / MinGW Makefiles / Ninja
- 无需 shell 脚本

### 6.2 新目录树结构

```
SWMF_Cross_Platform/                     # 新根目录
│
├── CMakeLists.txt                       # 顶层 CMake (项目定义 + 版本)
├── cmake/                               # CMake 模块
│   ├── FindSWMF.cmake                   # 依赖检测模块
│   ├── Platform.cmake                   # 平台特定设置
│   └── CompilerFlags.cmake              # 编译器标志管理
│
├── src/                                 # 源文件 (符号链接或复制自原始SWMF)
│   ├── share/                           # 共享库
│   │   └── Library/CMakeLists.txt
│   ├── CON/                             # 控制层
│   │   ├── Library/CMakeLists.txt
│   │   ├── Coupler/CMakeLists.txt
│   │   ├── Interface/CMakeLists.txt
│   │   ├── Control/CMakeLists.txt
│   │   └── Stubs/CMakeLists.txt
│   ├── GM/
│   │   └── Empty/CMakeLists.txt
│   ├── IE/
│   │   └── Empty/CMakeLists.txt
│   ├── IH/
│   │   └── Empty/CMakeLists.txt
│   ├── IM/
│   │   └── Empty/CMakeLists.txt
│   ├── EE/
│   │   └── Empty/CMakeLists.txt
│   ├── OH/
│   │   └── Empty/CMakeLists.txt
│   ├── SC/
│   │   └── Empty/CMakeLists.txt
│   ├── PC/
│   │   └── Empty/CMakeLists.txt
│   ├── PS/
│   │   └── Empty/CMakeLists.txt
│   ├── PT/
│   │   └── Empty/CMakeLists.txt
│   ├── PW/
│   │   └── Empty/CMakeLists.txt
│   ├── RB/
│   │   └── Empty/CMakeLists.txt
│   ├── SP/
│   │   └── Empty/CMakeLists.txt
│   ├── UA/
│   │   └── Empty/CMakeLists.txt
│   └── CZ/
│       └── Empty/CMakeLists.txt
│
├── util/                                # 工具库
│   ├── NOMPI/CMakeLists.txt
│   ├── TIMING/CMakeLists.txt
│   └── DATAREAD/CMakeLists.txt
│       ├── srcIndices/CMakeLists.txt
│       └── srcDemt/CMakeLists.txt
│
├── scripts/                             # Windows 编译脚本
│   ├── build_vs2022.bat                 # Visual Studio 2022
│   ├── build_mingw.sh                   # MinGW/MSYS2 (bash)
│   ├── build_mingw.bat                  # MinGW (cmd)
│   ├── setup_deps.ps1                   # 依赖安装 (PowerShell)
│   └── README_WINDOWS.md                # Windows 编译指南
│
├── .gitignore
└── README.md
```

### 6.3 CMake 构建策略

```
顶层 CMakeLists.txt:
  project(SWMF LANGUAGES Fortran C CXX)
  enable_language(Fortran)
  
  # 平台检测
  if(WIN32)
    set(SWMF_PLATFORM Windows)
  elseif(APPLE)
    set(SWMF_PLATFORM Darwin)
  else()
    set(SWMF_PLATFORM Linux)
  endif()
  
  # MPI 检测
  find_package(MPI REQUIRED COMPONENTS Fortran)
  
  # 构建库
  add_subdirectory(src/share/Library)     # libSHARE
  add_subdirectory(util/TIMING)           # libTIMING
  add_subdirectory(util/DATAREAD)         # libDATAREAD
  add_subdirectory(src/CON/Library)       # libLIBRARY
  add_subdirectory(src/CON/Coupler)       # libCOUPLER
  add_subdirectory(src/GM/Empty)          # libGM (stub)
  add_subdirectory(src/IE/Empty)          # libIE (stub)
  add_subdirectory(src/IH/Empty)          # libIH (stub)
  ... 所有组件 ...
  add_subdirectory(src/CON/Interface)     # libINTERFACE
  add_subdirectory(src/CON/Control)       # libCONTROL + SWMF.exe
```

---

## 7. 执行计划 (分阶段)

### Phase 1: 基础框架 (当前)
- [ ] 创建顶层 CMakeLists.txt
- [ ] 创建 cmake/ 模块目录
- [ ] 创建 src/share/Library/CMakeLists.txt (共享基础库)
- [ ] 创建空组件 wrapper (GM/Empty, IE/Empty, ...)
- [ ] 创建 CON 基础库链

### Phase 2: 控制层
- [ ] src/CON/Library/CMakeLists.txt
- [ ] src/CON/Coupler/CMakeLists.txt
- [ ] src/CON/Interface/CMakeLists.txt (22个耦合器)
- [ ] src/CON/Control/CMakeLists.txt (主程序SWMF.exe)
- [ ] src/CON/Stubs/CMakeLists.txt

### Phase 3: 组件实现
- [ ] 所有 16 个组件的 CMakeLists.txt (Empty stubs)
- [ ] 后续可逐步接入真实物理模型 (BATSRUS, Ridley_serial, ...)

### Phase 4: 工具库
- [ ] util/TIMING/CMakeLists.txt
- [ ] util/NOMPI/CMakeLists.txt
- [ ] util/DATAREAD/CMakeLists.txt
- [ ] util/EMPIRICAL/ (按需)

### Phase 5: Windows 编译验证
- [ ] MinGW/MSYS2 编译脚本
- [ ] 编译测试 (使用 stub 组件)
- [ ] 运行时验证 (NOMPI 模式)

---

## 8. 关键文件路径映射

| 原始 SWMF 位置 | 新位置 (SWMF_Cross_Platform) |
|---------------|---------------------------|
| `share/Library/src/*.f90` | `src/share/Library/*.f90` (链接) |
| `CON/Library/src/*.f90` | `src/CON/Library/*.f90` |
| `CON/Coupler/src/*.f90` | `src/CON/Coupler/*.f90` |
| `CON/Interface/src/*.f90` | `src/CON/Interface/*.f90` |
| `CON/Control/src/*.f90` | `src/CON/Control/*.f90` |
| `GM/Empty/src/GM_wrapper.f90` | `src/GM/Empty/GM_wrapper.f90` |
| `IE/Empty/src/IE_wrapper.f90` | `src/IE/Empty/IE_wrapper.f90` |
| ... | ... |
| `util/TIMING/src/*.f90` | `util/TIMING/*.f90` |
| `util/NOMPI/src/*.f90` | `util/NOMPI/*.f90` |
| `util/DATAREAD/srcIndices/*.f90` | `util/DATAREAD/srcIndices/*.f90` |

---

## 9. 注意事项

1. **源代码不动原则:** 新目录树使用 `file(COPY ...)` 或符号链接从原始 SWMF 目录引用源文件，绝不修改原始代码。

2. **^CMP 条件编译:** CMake 使用 `target_compile_definitions()` 来处理等价的条件编译。Fortran 源代码中的 `!^CMP IF XX` 预处理指令需要用 CMake 的 `add_definitions(-DXX)` 或通过 `.F90` 文件（大写后缀会被自动预处理）来控制。

3. **模块依赖顺序:** Fortran 的模块编译顺序非常关键。CMake 能自动分析 `USE` 语句确定编译依赖，但需要确保所有 `use` 的模块在同一 CMake 项目中。

4. **文件扩展名:** `.f90` (自由格式，不预处理) 和 `.F90` (自由格式，预处理) 在 CMake 中有区别。大写后缀 `.F90` 会经过 C 预处理器。

5. **编译模式选择:** 建议使用 Debug 模式进行初始验证 (`cmake -DCMAKE_BUILD_TYPE=Debug`)，使用 `-fdefault-real-8 -fdefault-double-8` 保持与原始代码双精度一致。
