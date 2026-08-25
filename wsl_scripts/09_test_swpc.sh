#!/bin/bash
cd /home/kosaka/swmf_fresh
export OMP_NUM_THREADS=8
make test_swpc TESTDIR=run_test_swpc > /home/kosaka/test_swpc_log.txt 2>&1
echo TEST_SWPC_EXIT=$?
tail -25 /home/kosaka/test_swpc_log.txt
