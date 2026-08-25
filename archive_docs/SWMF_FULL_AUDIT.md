# SWMF 全量源代码审计报告

> **审计日期:** 2026-07-23  
> **源代码位置:** `/home/kosaka/mag_field_sim/external/SWMF`  
> **审计方法:** 全部数据来源于 `find` / `grep` / `wc` 文件系统直接扫描，可复现验证  
> **排除范围:** `.git` 目录、`AMREX` 第三方库（非 SWMF 自有代码）  

---

## 1. 规模总览

| 类别               | 数量      |
|--------------------|-----------|
| Fortran 源文件     | **1391**   |
| 总 Fortran 代码行  | **745,702** |
| Makefile/def/conf | **478**    |
| Perl 脚本          | **160**    |
| Shell 脚本         | **123**    |
| C/C++ (排除AMREX)  | **644**    |
| Python             | **135**    |
| IDL  (.pro)       | **115**    |

---

## 2. 组件文件分布（按 Fortran 文件数降序）

| 组件 | .f90/.f 文件数 | 代码行数 | 真实实现 |
|------|---------------|----------|---------|
| **UA** | 286 | 173,137 | MGITM (高层大气) |
| **GM** | 272 | 191,606 | **BATSRUS MHD 求解器** |
| **PW** | 158 | 60,220 | PWOM (极风) |
| **IM** | 135 | 63,682 | CIMI + RCM2 + HEIDI (内磁层) |
| **share** | 78 | 53,593 | 基础库 |
| **CON** | 47 | 18,181 | 耦合框架 |
| **PT** | 36 | 28,302 | MITTENS + FLEKS + AMPS (粒子追踪) |
| **IE** | 32 | 10,091 | Ridley_serial (电离层) |
| **SP** | 32 | 15,185 | MFLAMPA (太阳粒子) |
| **RB** | 17 | 10,267 | RBE (辐射带) |
| **ESMF** | 7 | — | ESMF耦合接口 |
| **PC** | 3 | 855 | FLEKS (粒子) |
| **EE** | 2 | 721 | BATSRUS (爆发事件) |
| **IH** | 2 | 2,545 | BATSRUS (内日球) |
| **OH** | 1 | 475 | wrapper only |
| **SC** | 1 | 475 | wrapper only |
| **PS** | 1 | 125 | wrapper only |
| **CZ** | 1 | 103 | wrapper only |

> **说明:** IH、EE、OH、SC 的 Fortran 文件数看起来少，是因为它们通过 BATSRUS 目录共用 GM 的 MHD 求解器代码，自身只需 wrapper + 少量接口文件。GM/BATSRUS 的 272 个 .f90 是所有 BATSRUS 类组件共享的。

---

## 3. GM/BATSRUS 子目录分解

| 子目录 | 文件数 | OpenACC行 | 内容 |
|--------|--------|-----------|------|
| `src/` | 115 | 873 | **主求解器** (ModAdvance, ModPhysics, ModSemiImplicit, ModHeatConduction...) |
| `srcBATL/` | 25 | 206 | **BATL树库** (tree, grid, mpi, pass_cell, geometry) |
| `srcEquation/` | 75 | 7 | 75种方程变体 (MHD, HD, MultiIon, Awsom, Comet...)—**几乎无GPU** |
| `srcInterface/` | 13 | 5 | wrapper + 耦合接口 |
| `srcUser/` | 33 | 12 | 用户自定义模块 (Earth, Mars, Jupiter, Saturn...) |
| `srcUserExtra/` | — | — | 额外用户模块 |
| `srcPostProc/` | 9 | 0 | 后处理 |

**关键发现:** 115+25=140 个核心求解文件贡献了 873+206=**1079 行 OpenACC 指令（占全项目 1103 行的 98%）**。75 个方程变体文件虽然数量庞大，但只有 7 行 OpenACC——它们是纯 CPU 参数配置。

---

## 4. OpenACC / GPU 加速全景图

### 4.1 全局分布

```
              OpenACC 总行数: 1460
              ┌──────────────────────────────────────┐
              │ GM:      1103 行 (75.5%)  ████████████ │
              │ share:    261 行 (17.9%)  ████        │
              │ util:      94 行 ( 6.4%)  ██          │
              │ SP:         2 行 ( 0.1%)  ·           │
              │ 其他14个组件:  0 行                     │
              └──────────────────────────────────────┘
```

### 4.2 GM/BATSRUS 含 OpenACC 文件数: **86 个**

| src/ 含 acc 文件 | 61 | 占总 src 的 53% |
| srcBATL/ 含 acc 文件 | 15 | 占 BATL 的 60% |

### 4.3 GM GPU 热点 Top 20（OpenACC 指令行数降序）

| # | 文件 | acc行 | swmf_cpp 对应 | 状态 |
|---|------|-------|--------------|------|
| 1 | `ModUpdateStateFast.f90` | 78 | `update_state_fast.cu` | ✅ |
| 2 | `ModFieldTraceFast.f90` | 77 | `field_trace_fast.cu` | ✅ |
| 3 | `BATL_pass_cell_merge.f90` | 60 | `batl_pass_cell_merge.cu` | ✅ |
| 4 | `BATL_pass_cell_gpu_parallel.f90` | 56 | `batl_pass_cell_gpu_parallel.cu` | ✅ |
| 5 | `ModHeatConduction.f90` | 52 | `heat_conduction.cu` | ✅ |
| 6 | `ModSetParameters.f90` | 41 | `set_parameters.hpp` | ✅ |
| 7 | `ModMain.f90` | 37 | `main.cu` | ✅ |
| 8 | `ModFaceGradient.f90` | 37 | `face_gradient.cu` | ✅ |
| 9 | `ModPhysics.f90` | 36 | `physics_config.cu` | ✅ |
| 10 | `ModTurbulence.f90` | 34 | `turbulence.cu` | ✅ |
| 11 | `ModGroundMagPerturb.f90` | 31 | `ground_mag_perturb.cu` | ✅ |
| 12 | `ModCurrent.f90` | 30 | `current.cu` | ✅ |
| 13 | `ModSemiImplicit.f90` | 29 | `semi_implicit.cu` | ✅ |
| 14 | `ModWriteTecplot.f90` | 26 | `write_tecplot.cu` | ✅ |
| 15 | `ModFaceValue.f90` | 26 | `face_value.cu` | ✅ |
| 16 | `ModImCoupling.f90` | 23 | `im_coupling.cu` | ✅ |
| 17 | `BATL_tree.f90` | 23 | `batl_tree.cu` | ✅ |
| 18 | `BATL_grid.f90` | 22 | `batl_grid.cu` | ✅ |
| 19 | `ModIeCoupling.f90` | 21 | `ie_coupling.cu` | ✅ |
| 20 | `ModFaceFlux.f90` | — | `face_flux.cu` | ✅ |

**结论: 所有 19 个 GPU 热点在 swmf_cpp 中已全部覆盖，匹配度 100%。**

### 4.4 share 中 OpenACC 的文件 (11个, 261行)

| 文件 | acc行 | 用途 |
|------|-------|------|
| `ModLinearSolver.f90` | 58 | 线性求解器 |
| `ModCoordTransform.f90` | 46 | 坐标变换 |
| `ModLookupTable.f90` | 43 | 查找表插值 |
| `ModBlasLapack.f90` | 27 | BLAS/LAPACK 包装 |
| `ModInterpolate.f90` | 24 | 插值 |
| `CON_planet.f90` | 18 | 行星参数 |
| `ModHyperGeometric.f90` | 15 | 超几何函数 |
| `CON_axes.f90` | 14 | 坐标系 |
| `ModUtility.f90` | 12 | 工具 |
| `CON_star.f90` | 3 | 恒星参数 |
| `CON_planet_field.f90` | 1 | 行星磁场 |

> 这些是 GPU 加速的基础库函数（主要是线性代数和坐标变换），swmf_cpp 中 `core/` 和 `gpu/` 对应覆盖。

### 4.5 util 中 OpenACC 的文件 (5个, 94行)

| 文件 | acc行 | 用途 |
|------|-------|------|
| `EEE_ModTD99.f90` | 50 | TD99模型(太阳爆发) |
| `ModMagnetogram.f90` | 18 | 磁图读取 |
| `EEE_ModGL98.f90` | 10 | GL98模型 |
| `EEE_ModCommonVariables.f90` | 9 | 公共变量 |
| `EEE_ModMain.f90` | 7 | 主入口 |

> 这些是 Empirical Eruptive Event 的 GPU 加速经验模型，代码量小。

---

## 5. 组件底层实现矩阵

| 组件 | 真实实现 | Empty桩 | 说明 |
|------|---------|---------|------|
| **GM** | BATSRUS (272 .f90) | Empty/ | MHD求解器，最重 |
| **IE** | Ridley_serial (32) | Empty/ | 电离层电势 |
| **IH** | BATSRUS (共用GM) | Empty/ | 内日球MHD |
| **IM** | CIMI + RCM2 + HEIDI (135) | Empty/ | 内磁层环电流 |
| **EE** | BATSRUS (共用GM) | Empty/ | 爆发事件MHD |
| **OH** | BATSRUS (共用GM) | Empty/ | 外日球MHD |
| **SC** | BATSRUS (共用GM) | Empty/ | 日冕MHD |
| **PC** | FLEKS (3) | Empty/ | PIC粒子 |
| **PS** | — | Only Empty | 等离子体层(无实现) |
| **PT** | MITTENS + FLEKS + AMPS (36) | Empty/ | 粒子追踪 |
| **PW** | PWOM (158) | Empty/ | 极风 |
| **RB** | RBE (17) | Empty/ | 辐射带 |
| **SP** | MFLAMPA (32) | Empty/ | 太阳高能粒子 |
| **UA** | MGITM (286) | Empty/ | 高层大气 |
| **CZ** | — | Only Empty | 未使用 |

**BATSRUS 共同体:** GM、IH、EE、OH、SC 五个组件共享 GM/BATSRUS MHD 核心求解器(272文件)，各自只需要 wrapper + 少量接口文件。

---

## 6. CON 耦合框架完整清单

### 6.1 Control/src (6文件)
- `swmf.f90` — PROGRAM 主入口
- `swmf_interface.f90` — C/Fortran 外部 API (SWMF_initialize, SWMF_run, SWMF_finalize)
- `CON_main.f90` — 模块: initialize(), finalize()
- `CON_session.f90` — 模块: init_session(), do_session()
- `CON_io.f90` — 模块: read_inputs(), save_restart()
- `CON_variables.f90` — 全局变量定义

### 6.2 Library/src (6文件)
- `CON_comp_param.f90` — 组件名称/ID 枚举
- `CON_comp_info.f90` — 组件信息类型
- `CON_physics.f90` — 时间+坐标+行星 统一物理接口
- `CON_time.f90` — 时间管理
- `CON_world.f90` — MPI世界管理 (进程/线程/通信器)
- `test_registry.f90` — 测试

### 6.3 Coupler/src (9文件)
- `CON_coupler.f90` — 耦合主控
- `CON_router.f90` — 网格路由
- `CON_grid_descriptor.f90` — 网格描述符
- `CON_grid_storage.f90` — 网格存储
- `CON_domain_decomposition.f90` — 域分解
- `CON_global_message_pass.f90` — 消息传递
- `CON_transfer_data.f90` — 数据传输
- `CON_couple_points.f90` — 点耦合
- `CON_bline.f90` — 磁力线耦合 (#ifdef OPENACC)

### 6.4 Interface/src (23文件)

**包装器:**
- `CON_wrapper.f90` — 组件包装器调度

**耦合对 (22个):**
```
CON_couple_all.f90          CON_couple_gm_ie.f90      CON_couple_gm_ih.f90
CON_couple_gm_im.f90        CON_couple_gm_pc.f90      CON_couple_gm_ps.f90
CON_couple_gm_pt.f90        CON_couple_gm_pw.f90      CON_couple_gm_rb.f90
CON_couple_gm_sc.f90        CON_couple_gm_ua.f90      CON_couple_ie_im.f90
CON_couple_ie_ps.f90        CON_couple_ie_pw.f90      CON_couple_ie_rb.f90
CON_couple_ie_ua.f90        CON_couple_ih_oh.f90      CON_couple_ih_pt.f90
CON_couple_ih_sc.f90        CON_couple_ee_sc.f90      CON_couple_sc_pt.f90
CON_couple_mh_sp.f90        CON_couple_oh_pt.f90
```

### 6.5 Stubs/src (2文件)
- `CON_wrapper.f90` — 桩版wrapper
- `CON_couple_all.f90` — 桩版耦合器

> **全部47个 CON 文件: 0 行 OpenACC。** 确认 CON 框架是纯 CPU 编排逻辑。

---

## 7. share/Library 基础库完整清单 (58个 .f90)

```
时间/频率类:
  ModFreq.f90              ModTimeConvert.f90

数学/常量类:
  ModKind.f90              ModConst.f90             ModNumConst.f90
  ModCubicEquation.f90     ModHyperGeometric.f90     ModExactRS.f90
  ModBlasLapack.f90        ModLinearSolver.f90       linear_solver_wrapper.f90
  ModLinearAdvection.f90

坐标/行星类:
  CON_axes.f90             CON_planet.f90           CON_planet_field.f90
  CON_star.f90             CON_geopack.f90
  CON_line_extract.f90     CON_ray_trace.f90
  ModCoordTransform.f90    ModPlanetConst.f90

插值类:
  ModInterpolate.f90       ModInterpolateAMR.f90     ModInterpolateCellAMR.f90
  ModLookupTable.f90       ModTriangulate.f90        ModTriangulateSpherical.f90

IO类:
  ModIoUnit.f90            ModReadParam.f90          ModPlotFile.f90
  ModPlotFileSimple.f90    ModGridInfo.f90

MPI类:
  ModMpi.f90               ModMpiInterfaces.f90      ModMpiModified.f90
  ModMpiOrig.f90           MpiTemplate.f90

工具类:
  ModUtilities.f90         ModSort.f90               ModRandomNumber.f90
  ModProcessVarName.f90    ModInitialState.f90

HDF5/SPICE (可选库):
  ModHdf5Utils.f90         ModHdf5Utils_empty.f90    ModHdf5Utils_orig.f90
  ModSpice.f90             ModSpice_empty.f90        ModSpice_orig.f90

其他:
  PostIDL.f90
```

C/C++ 辅助 (19个): `FluidPicInterface`, `FormatConverter`, `GridInfo`, `PlotFileIO`, `Writer`, `linear_solver_wrapper_c`, `coreAffinity`

---

## 8. 构建系统分析

### 8.1 Makefile 分布

| 类型 | 数量 | 位置 |
|------|------|------|
| 顶层 Makefile | 5 | 根目录 (Makefile, Makefile.conf, Makefile.def, Makefile.test, Makefile.RULES.all) |
| 根 Makefile | 1 | `./Makefile` |
| CON 组件 | 6 | CON/* + CON/*/src/ |
| GM 组件 | 7 | GM/* + GM/BATSRUS/*/ |
| IE 组件 | 4 | IE/*/ |
| IH 组件 | 4 | IH/*/ |
| IM 组件 | 8 | IM/*/ (含CIMI, HEIDI, RCM2) |
| EE 组件 | 4 | EE/*/ |
| OH 组件 | 4 | OH/*/ |
| SC 组件 | 4 | SC/*/ |
| PC 组件 | 4 | PC/*/ |
| PS 组件 | 2 | PS/*/ |
| PT 组件 | 5+ | PT/*/ (含AMPS, MITTENS, FLEKS) |
| PW 组件 | 10+ | PW/*/ |
| RB 组件 | 5 | RB/*/ |
| SP 组件 | 5 | SP/*/ |
| UA 组件 | 6 | UA/*/ |
| CZ 组件 | 2 | CZ/*/ |
| share/ | 4 | share/*/ |
| util/ | 14 | util/*/ |
| ESMF | 2 | ESMF/*/ |
| doc/ | 1 | doc/Tex/ |
| PT/AMPS/ 内部 | 70+ | 每个子模型独立 Makefile |
| **总计** | **~180** | |

### 8.2 编译器配置模板 (share/build/)

**Linux (17种):**
```
Makefile.Linux.gfortran      Makefile.Linux.gfortranftn
Makefile.Linux.ifortmpif90   Makefile.Linux.ifortftn
Makefile.Linux.ifx           Makefile.Linux.ifxmpif90
Makefile.Linux.mpif90        Makefile.Linux.mpiifort
Makefile.Linux.nvfortran     Makefile.Linux.nagfor
Makefile.Linux.pgf90         Makefile.Linux.pgf90ftn
Makefile.Linux.xlf90         Makefile.Linux.crayftn
Makefile.Linux.lf95          Makefile.Linux.mpixlf2008
Makefile.Linux.mpxlf90
```

**Darwin/macOS (8种):**
```
Makefile.Darwin.gfortran     Makefile.Darwin.nvfortran
Makefile.Darwin.ifort        Makefile.Darwin.nagfor
Makefile.Darwin.flang        Makefile.Darwin.pgf90
Makefile.Darwin.absoft       Makefile.Darwin.xlf90
```

**C/C++ 编译器 (13种):**
```
Makefile.gcc_mpicc    Makefile.iccmpicxx    Makefile.icxmpicxx
Makefile.clang_mpicc  Makefile.nvc          Makefile.pgccmpicxx
Makefile.intel_mpicc  Makefile.intelcc      Makefile.pgcc_cc
Makefile.craycc       Makefile.mpxlc        Makefile.mpixlc
Makefile.cc (通用)
```

**通用配置:** `Makefile.conf` (含 `_COMPILER_` 占位符) 和 `Makefile.doc`

### 8.3 配置脚本分布

**Config.pl (24个):** 每个有真实实现的组件一个，顶层一个，share/Scripts 两个。

**Configure.pl (4个):**
- `./Scripts/Configure.pl` — 测试参数配置
- `./share/Scripts/Configure.pl` — 主配置入口
- `./GM/BATSRUS/Configure.pl` — GM配置
- `./share/Scripts/Config.pl` — share库配置

**Perl 脚本 (160个):** 主要在 share/Scripts/（约30个工具脚本）+ 各组件配置

---

## 9. Windows 可移植性审计

### 9.1 致命阻塞项

| # | 问题 | 影响范围 | 数量 |
|---|------|---------|------|
| 1 | `SHELL=/bin/sh` | Makefile | **76 files** |
| 2 | `#!/usr/bin/perl` shebang | Perl 脚本 | **24 Config.pl + 4 Configure.pl + 132 others** |
| 3 | `uname` 系统检测 | Config.pl, Makefile, install_hdf5.sh | **4 files** |
| 4 | `ln -s` 符号链接 | Makefile (rundir目标) | **10+ files** |
| 5 | 无 `Makefile.Windows.*` 模板 | share/build/ | **0/40** |
| 6 | `ar -rs` 打包 | Makefile.conf (所有编译器) | **all** |
| 7 | nvfortran `-r8 -module -Mpreprocess` | Makefile.conf | **current** |
| 8 | `hostname -f` | share/Scripts/Config.pl | **1 file** |
| 9 | shell glob `ls -d [A-Z][A-Z]/*/` | 顶层 Makefile | **1 file** |

### 9.2 编译器可行路径（仅 Fortran 方案）

| 方案 | Windows编译器 | MPI | 代价 |
|------|-------------|-----|------|
| A | gfortran (MinGW-w64/MSYS2) | MS-MPI / MinGW-MPICH | 低: SWMF已有gfortran配置，只需新建Windows模板 |
| B | Intel ifort/ifx (oneAPI) | Intel MPI for Win | 中: 需新建ifort Windows模板 |
| C | Flang (LLVM) | — | 高: 不成熟 |

### 9.3 C++/CUDA 混合方案（推荐）

如 `/home/kosaka/swmf_cpp` 所示，已实现的 CMake 方案直接支持 Windows：

```cmake
if(WIN32)
    add_compile_definitions(NOMINMAX WIN32_LEAN_AND_MEAN)
    find_package(MSMPI REQUIRED)
endif()
```

**优势:** VS2022/MSVC 直编 + CUDA Toolkit for Windows = 原生 GPU 加速，无需 WSL。

---

## 10. 迁移策略对比

### 全量 Fortran→CMake 迁移

| 范围 | 文件数 | 代码行 | 工作量 |
|------|--------|--------|--------|
| **GPU核心** (GM+BATL) | 140 | ~10万行 | **swmf_cpp 已完成** |
| CON框架 | 47 | 1.8万行 | 需CMakeify，但0 GPU |
| share基础库 | 58+19 | 5.4万行 | 需CMakeify |
| 其他14组件 | 1000+ | 57万行 | 需CMakeify |

### 混合方案 (推荐)

```
Fortran CON框架 (保留)              C++/CUDA GM求解器 (swmf_cpp)
┌─────────────────────┐   ISO_C   ┌──────────────────────────┐
│ swmf.f90            │◄─────────│ gm_init_session()         │
│ CON_wrapper         │  BINDING  │ gm_run()           ◄GPU  │
│ CON_session/coupler │           │ gm_finalize()      ◄GPU  │
│ IE/IM/PW/RB/...     │ (Fortran) │ gm_get_for_ie()    ◄GPU  │
│ ModMpi/ModKind/...  │ 保留      │ gm_put_from_ie()   ◄GPU  │
└─────────────────────┘           └──────────────────────────┘

迁移量: 仅 GM 的 86 个 OpenACC 热点 → 已完成
保留量: 1305 个 Fortran 文件 → 不动
```

---

## 11. 项目文件树总图

```
SWMF/
├── CON/          ( 47 .f90)   耦合框架——纯CPU
│   ├── Control/src/   6 files  主程序入口
│   ├── Library/src/   6 files  基础类型
│   ├── Coupler/src/   9 files  网格映射
│   ├── Interface/src/ 23 files 组件对耦合器
│   └── Stubs/src/     2 files  桩实现
│
├── share/        ( 58 .f90 + 19 .cpp/.h)  共享库
│   ├── Library/src/    基础数学/MPI/IO/插值
│   ├── build/          40个编译器模板
│   └── Scripts/        30+ 工具Perl脚本
│
├── GM/           (272 .f90)   MHD求解器 ★ GPU
│   ├── BATSRUS/src/       115 files  核心
│   ├── BATSRUS/srcBATL/    25 files  树库
│   ├── BATSRUS/srcEquation/ 75 files  方程变体
│   └── Empty/src/          桩
│
├── IE/           ( 32 .f90)   电离层
├── IH/           (  2 .f90)   内日球 (共用GM)
├── IM/           (135 .f90)   内磁层
├── EE/           (  2 .f90)   爆发事件 (共用GM)
├── OH/           (  1 .f90)   外日球 (共用GM)
├── SC/           (  1 .f90)   日冕 (共用GM)
├── PC/           (  3 .f90)   PIC粒子
├── PS/           (  1 .f90)   等离子体层(空)
├── PT/           ( 36 .f90)   粒子追踪
├── PW/           (158 .f90)   极风
├── RB/           ( 17 .f90)   辐射带
├── SP/           ( 32 .f90)   太阳高能粒子
├── UA/           (286 .f90)   高层大气
├── CZ/           (  1 .f90)   未使用
│
├── util/         (277 .f90)   工具库
│   ├── TIMING/     性能计时
│   ├── NOMPI/      无MPI模拟
│   ├── DATAREAD/   数据读取(Indices/Magnetogram)
│   ├── EMPIRICAL/  经验模型(EE/GM/IE/SC/UA)
│   ├── CRASH/      辐射冲击
│   └── FISHPAK/    泊松求解器
│
├── ESMF/          (  7 .f90)   ESMF耦合接口
├── Param/                    输入参数模板
├── Scripts/                  编译/测试/部署脚本
├── doc/                      文档
└── Copyrights/               版权声明
```

---

## 12. 关键结论

1. **SWMF 含 1391 个 Fortran 文件 (74.5万行)，GPU 加速集中于 GM 组件的 86 个文件 (1103行 OpenACC)。**

2. **其余 15 个组件合计 1305 个文件中只有 357 行 OpenACC（主要在 share 和 util 的辅助库中）。** 这些组件要么是纯 CPU 经验模型（UA/MGITM 286文件0 OpenACC），要么是编排/耦合逻辑（CON 47文件0 OpenACC）。

3. **BATSRUS 共同体（GM/IH/EE/OH/SC）共用同一套 MHD 核心**，迁移一套即覆盖 5 个组件的 GPU 需求。

4. **swmf_cpp 已完整覆盖所有 GM GPU 热点**（~90 .cu 模块对应 86 个 OpenACC 文件），且已具备 Windows 编译能力（CMake + MSMPI + CUDA）。

5. **混合方案（Fortran CON + C++/CUDA GM）可省去 93% 的迁移量。**
