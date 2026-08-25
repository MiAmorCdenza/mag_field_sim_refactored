#!/bin/bash
echo '===== SYSTEM ==='
nproc; free -g | head -2
df -h / /mnt/c 2>/dev/null | head -4
cat /mnt/c/Users/Admin/.wslconfig 2>/dev/null || echo '(no .wslconfig)'
echo '===== HPC SDK ==='
ls /opt/nvidia/hpc_sdk/Linux_x86_64/26.5/compilers/bin/ 2>/dev/null | head -10
ls /opt/nvidia/hpc_sdk/modulefiles/ 2>/dev/null
echo '===== MPI ==='
which mpirun mpifort 2>/dev/null
echo '===== GIT REMOTES ==='
for d in ~/SWMF ~/SWMF_repo ~/SWMF_Cross_Platform; do
  echo "-- $d"
  git -C $d remote -v 2>/dev/null | head -4
  git -C $d log --oneline -1 2>/dev/null
  git -C $d status -sb 2>/dev/null | head -3
done
echo '===== SWMF DIR SIZES ==='
du -sh ~/SWMF ~/SWMF_repo ~/SWMF_Cross_Platform ~/SWMF_data 2>/dev/null
echo '===== SWMF_Cross_Platform contents ==='
ls ~/SWMF_Cross_Platform | head -20
echo '===== SWMF_data contents ==='
ls ~/SWMF_data | head -20
echo '===== run dirs & PARAM.in ==='
ls ~/SWMF_repo/run/ 2>/dev/null | head -10
find ~/SWMF_repo -maxdepth 3 -name 'PARAM.in' 2>/dev/null | head -8
find ~/SWMF_repo -maxdepth 3 -name 'GM/Param*.in' -o -maxdepth 3 -name 'test_magnetosphere*' 2>/dev/null | head -6
echo '===== WSL mag_field_sim ==='
ls ~/mag_field_sim 2>/dev/null | head -15
echo '===== toolchain in WSL ==='
which gfortran gcc make cmake python3 2>/dev/null
echo 'DONE'
