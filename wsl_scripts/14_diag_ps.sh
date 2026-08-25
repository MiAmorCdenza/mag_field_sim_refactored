#!/bin/bash
cd /home/kosaka/swmf_fresh/run_magfield
rm -f runlog6 ps.log run.exit6
# per-process RSS sampler
setsid nohup bash -c 'while true; do echo "=== $(date +%H:%M:%S) ===" >> ps.log; ps -eo pid,rss,comm --sort=-rss | head -12 >> ps.log; sleep 2; done' >/dev/null 2>&1 &
setsid nohup bash -c 'OMP_NUM_THREADS=6 mpiexec -n 6 ./SWMF.exe > runlog6 2>&1; echo EXIT=$? > run.exit6' >/dev/null 2>&1 &
sleep 3; pgrep -f SWMF.exe | head -1
