# SWMF 部署与运行清单(WSL 验证版 → 服务器复用)

> 本清单在 WSL (Ubuntu, gfortran + OpenMPI, 32 线程) 上完整验证,服务器到货后按同样步骤执行,仅需调整编译选项与进程布局。

## 0. 已验证环境快照(WSL)
- Ubuntu (WSL2), gfortran 15.2 + OpenMPI (apt), make/git/python3
- NVIDIA HPC SDK 26.5 已装于 /opt/nvidia/hpc_sdk(本清单未使用;GPU 版另行验证)

## 1. 获取代码
```bash
cd ~
git clone --depth 1 https://github.com/SWMFsoftware/SWMF.git swmf_fresh
cd swmf_fresh
./Config.pl -clone            # 拉取组件仓库 (GM/BATSRUS, IE/Ridley_serial, IM/RCM2, ...)
```

## 2. 数据软链(需要 SWMF_data)
```bash
ln -s ~/SWMF_data/GM/BATSRUS/data GM/BATSRUS/data
for c in IM/RCM2 IM/CIMI IM/HEIDI PT/MITTENS PW/PWOM UA/MGITM; do
  [ -d ~/SWMF_data/$c/data ] && ln -s ~/SWMF_data/$c/data $c/data
done
```

## 3. 配置与编译(CPU 版,已验证)
```bash
./Config.pl -default
./Config.pl -v=Empty,GM/BATSRUS,IE/Ridley_serial,IM/RCM2
./Config.pl -o=GM:u=Default,e=Mhd,ng=2,g=8,8,8,IE:g=181,361
make -j 32 SWMF PIDL INTERPOLATE
# 产物: bin/SWMF.exe (~10.9 MB, 含全部物理), bin/PostIDL.exe, bin/INTERPOLATE.exe
```
- 注意: \`Config.pl -install\` 默认只装 Empty 桩,必须用 \`-v=\` 显式选物理组件。
- 服务器 GPU 版: 同法但 \`-compiler=nvfortran\`,Makefile.conf 打开 \`ACCFLAG=-D_OPENACC\`,加 \`-acc -gpu=cc70,cc80\` (V100=cc70)。

## 4. 运行目录与标准磁层算例(已验证)
```bash
make rundir RUNDIR=~/swmf_fresh/run_magfield
cd run_magfield
cp ../Param/SWPC/PARAM.in_SWPC_simple_init PARAM.in
cp ../Param/SWPC/{IMF.dat,SATELLITES.in,magin_GEM.dat,INTERPOLATE.in,sat01.dat} .
# 可选: 在时变段 #SAVEPLOT 加 '3d MHD tec' 输出 (用 wsl_scripts/adapt_param.py)
```

## 5. 启动(进程布局)
```bash
export OMP_NUM_THREADS=14
mpiexec -n 4 ./SWMF.exe > runlog 2>&1
# COMPONENTMAP (production): GM ranks 0-1 (x14 threads), IE ranks 2-3, IM rank 2
```
- 服务器 EPYC 9845 192 核建议: \`mpiexec -n 8\`,GM 6 ranks × 24 threads。
- 关键指标: 初始化 700+1500 步局部时间步进,然后 7200s 时变;跨极盖电位 ~90-110 kV 为正常。

## 6. 输出提取(已验证管线)
```bash
python3 wsl_scripts/extract_grid.py run_magfield/GM/IO2 <out_dir>
# 产出一致网格 npz: rho ux uy uz bx by bz p + ex ey ez (E=-u×B)
# full_1Re:  x∈[-90,25] y,z∈[-45,45] @1 Re
# inner_0.25Re: x∈[-20,10] y,z∈[-12,12] @0.25 Re
```

## 7. 已知坑位
1. \`Config.pl -install\` 忘加 \`-v=\` → 全 Empty 桩,SWMF.exe 仅 3.3 MB(真物理版 10.9 MB)。
2. \`make | tail\` 会吞掉 make 失败码,务必落盘日志查 \`MAKE_EXIT\`。
3. IMF.dat 只覆盖前 7 分钟,SWMF 会用最后值外推(正常行为)。
4. adapt_param.py 旧版有 off-by-10 字符 bug(#BORIS 被吃),已修复为精确正则替换。
5. 前任遗留: SWMF_data 必须软链,否则 PW 等测试因缺 restart 文件 MPI_ABORT(见 debug-swmf-test1-mpi-abort.md)。
6. 服务器到货验证: \`nvidia-smi nvlink -s\` 测 V100 桥;GPU 版另跑 \`make test_swpc_gpu\` 或 TESTACC 对拍。

## 7.5 磁盘纪律(每条件扫描)
- **每条件最终保留** ≈ 110 MB: npz(42+52 MB)+ 2D 切面 .dat(~12 MB)+ 日志
- **瞬时中间产物**(用完即删)≈ 700 MB: 3D .idl(~220 MB)/.tree/.info + 3D .dat(446 MB)
- 流程: run → pIDL 转 tec → extract_tec16.py 出 npz → **rm .idl/.tree/.info** → .dat 移入 ~/swmf_archive(ext4, 880 GB 富余) → npz+2D 拷回工作区
- 模板: wsl_scripts/post_scan.sh TAG;IMF 条件生成: wsl_scripts/make_imf.py
- 时变预测的数据量按帧数翻倍,本地 C:(79 GB 余)不承载 → 服务器战役再启用

## 8. 本机参数速查
- 磁盘: WSL ext4 882 GB 空闲 (C: 仅 84 GB,大数据落 ext4 再拷回工作区)
- 内存: WSL 16 GB + 8 GB swap (.wslconfig: memory=17179869184, swap=8589934592);算例 -n 6 运行正常
- 观测: -n 6 (GM 4 ranks × 6 threads = 24t) 相位1 ~0.19 s/步,约为 2-rank 布局的 3 倍速
- ⚠️ 运行期间勿执行 wsl --shutdown 或改 .wslconfig(算例在 VM 内会被直接带走)
- ⚠️ MaxBlock 压到 1200 会报 do_amr: could not fit blocks(标准值 5000 勿动)
- ⚠️ 会话3 关 IM 时须同步删 #COUPLE2/#COUPLEORDER 的 IM 引用,否则 SWMF_ERROR: IM is OFF
