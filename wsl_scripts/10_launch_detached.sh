#!/bin/bash
cd /home/kosaka/swmf_fresh/run_magfield
rm -f runlog2 run.exit run.pid
setsid nohup bash -c 'OMP_NUM_THREADS=12 mpiexec -n 4 ./SWMF.exe > runlog2 2>&1; echo $? > run.exit' >/dev/null 2>&1 &
sleep 3
PID=$(pgrep -f 'SWMF.exe' | head -1)
echo "launched, first pid=$PID"
echo $PID > run.pid
