#!/bin/bash
cd /home/kosaka/swmf_fresh/run_magfield
rm -f runlog5 mem.log dmesg.log run.exit5
# watcher: memory + dmesg sampler
setsid nohup bash -c 'while true; do date +%H:%M:%S >> mem.log; free -g >> mem.log; sleep 5; done' >/dev/null 2>&1 &
setsid nohup bash -c 'while true; do dmesg | tail -3 >> dmesg.log; sleep 5; done' >/dev/null 2>&1 &
# instrumented run
setsid nohup bash -c 'OMP_NUM_THREADS=6 mpiexec --mca mpi_abort_print_stack 1 --mca mpi_abort_delay 120 -n 6 ./SWMF.exe > runlog5 2>&1; echo EXIT=$? > run.exit5' >/dev/null 2>&1 &
sleep 3; pgrep -f SWMF.exe | head -1
