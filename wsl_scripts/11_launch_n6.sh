#!/bin/bash
cd /home/kosaka/swmf_fresh/run_magfield
rm -f runlog3 run.exit3
setsid nohup bash -c 'OMP_NUM_THREADS=6 mpiexec -n 6 ./SWMF.exe > runlog3 2>&1; echo $? > run.exit3' >/dev/null 2>&1 &
sleep 3
pgrep -f 'SWMF.exe' | head -1
