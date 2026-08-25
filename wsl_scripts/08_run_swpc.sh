#!/bin/bash
cd /home/kosaka/swmf_fresh/run_magfield
export OMP_NUM_THREADS=14
date '+%Y-%m-%d %H:%M:%S RUN START'
mpiexec -n 4 ./SWMF.exe > runlog 2>&1
echo RUN_EXIT=$?
date '+%Y-%m-%d %H:%M:%S RUN END'
tail -40 runlog
