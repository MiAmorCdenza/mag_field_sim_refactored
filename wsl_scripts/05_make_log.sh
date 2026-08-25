#!/bin/bash
cd /home/kosaka/swmf_fresh
export OMP_NUM_THREADS=1
make -j 32 SWMF PIDL > /home/kosaka/build_log_make.txt 2>&1
echo MAKE_EXIT=$?
tail -30 /home/kosaka/build_log_make.txt
