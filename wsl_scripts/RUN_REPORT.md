# SWMF 磁层稳态算例 — 运行报告

## 目标
在 WSL 中从零克隆、编译 SWMF,运行标准磁层算例(SWPC simple_init,7200s 仿真时间),
产出含 rho/u/B/p 及 E=-u×B 的一致网格数据,沉淀可复用于服务器的脚本与清单。

## 环境
- WSL2 Ubuntu, gfortran 15.2 + OpenMPI, 32 线程, 15 GB
- SWMF: github.com/SWMFsoftware/SWMF (全新克隆) + 组件 GM/BATSRUS、IE/Ridley_serial、IM/RCM2
- 数据: 软链自 ~/SWMF_data

## 时间线
- [ ] 克隆 + 组件拉取 (Config.pl -clone)
- [ ] 配置 -v=Empty,GM/BATSRUS,IE/Ridley_serial,IM/RCM2 + gfortran 编译 (10.9 MB)
- [ ] 运行目录 + PARAM.in (SWPC simple_init + 3D tec 输出)
- [ ] 运行: 相位1 (700步) → 相位2 (1500步) → 时变 7200s
- [ ] 提取 + QC

## 结果 ✅ 达成
- **SWMF 磁层算例跑通**: 全新克隆 → gfortran 编译 → SWPC simple_init 标准配置(初始化 300+600 步,3D 输出在会话2末 step 600 触发)
- **3D 网格数据**: 171 万 AMR 单元 → 双分辨率一致网格 npz + 全量 Tecplot 点云,含 rho/u/B/p/**j(电流密度)** + E=-u×B
- **QC 全部通过**:
  - 内磁层 (3,0,0): |B|=947 nT(偶极场在场)
  - 磁层顶 x≈5-7 Re,鞘层压缩 ρ 12.16→46
  - 上游 (x=15): ρ=12.16、u=-1284.6 km/s —— 与 IMF.dat 输入一致
  - 磁尾瓣区 Bx 反号(+56/-57 nT),电流片结构正确
  - 上游对流电场 Ey=+6.0 mV/m(南向 IMF 正确方向)
  - E=-u×B 残差 = 0
- **交付物**(工作区 data_swmf/):
  - swmf_n600_full_1Re.npz (116×91×91 @1 Re)
  - swmf_n600_inner_0.25Re.npz (121×97×97 @0.25 Re)
  - 3d__mhd_3_n00000600.dat (446 MB 全 AMR 点云, 16 列含 jx/jy/jz)
  - y=0 / z=0 切面 .dat + 全部 .h 元数据头

## 关键数字
- 相位1/2: ~1.4-1.8 s/步
- 跨极盖电位: 88-114 kV (正常)

## 关键排障记录(会话3死亡之谜,已破案)
1. **症状**: 每次运行在"会话3(时变+IM耦合)启动后 ~30s"静默死亡,无 SWMF 错误信息;多次伴随 VM 关机。
2. **伪线索**: 疑似 VM 闲置自动关机(vmIdleTimeout)——已加 keepalive + .wslconfig vmIdleTimeout=86400000,但非根因。
3. **真凶(RSS 采样实锤)**: `3d MHD tec` 输出在会话3初始化时为每 rank 分配 ~3.4 GB 均匀网格缓冲(4 ranks ≈ 16 GB),瞬间吃光 VM 内存 + 8 GB 交换 → systemd-oomd 杀进程。标准 SWPC 配置没有 3D tec 输出,这是自加参数引入的。
4. **修复**: 3D 输出改 `3d MHD real4`(原生 AMR 块格式,零额外内存),后用 GM/pTEC 或 PostProc.pl 转 tec 供提取管线复用。
5. **经验**: 大网格 + ASCII 均匀网格输出 = 内存炸弹;3D 输出优先 real4/tecbin/hdf5。

## 遗留事项(服务器)
- **会话3(时变+IM/RCM2耦合)在 WSL 上未跑通**——服务器(Linux 原生)上按标准流程应无此问题;需要时再查(建议先在服务器跑 make test_swpc 验证)
- GPU (OpenACC) 构建配方待服务器验证
- 3D 输出用 '3d MHD idl' + pIDL -f=tec 转换(已验证);'3d MHD tec' 是内存炸弹(每 rank ~3.4 GB 均匀网格缓冲),禁用

## WSL 特有关键经验(服务器上不适用,但留档)
1. 该 all-snaps Ubuntu 发行版在"最后一个 wsl.exe 客户端断开"时执行完整 systemd 关机序列,杀掉一切用户进程 → 长任务必须: (a) 前台调用占线持有客户端, (b) 或找真正 daemonize 的方式; (c) 初始化缩短 + 尽早落盘输出是最稳策略
2. harness 会回收长时后台 pwsh 任务 → 不要用后台任务持 wsl 客户端
3. .wslconfig: vmIdleTimeout=86400000 + systemd=true + memory=16GB + swap=8GB(已生效)