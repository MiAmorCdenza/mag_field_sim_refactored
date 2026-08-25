#!/bin/bash
cd /home/kosaka/swmf_fresh/run_magfield
rm -f runlog4 run.exit4
setsid nohup bash -c 'OMP_NUM_THREADS=6 mpiexec -n 6 ./SWMF.exe > runlog4 2>&1; echo $? > run.exit4' >/dev/null 2>&1 &
sleep 3
pgrep -f 'SWMF.exe' | head -1
