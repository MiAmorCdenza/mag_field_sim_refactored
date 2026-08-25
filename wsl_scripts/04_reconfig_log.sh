#!/bin/bash
cd /home/kosaka/swmf_fresh
export OMP_NUM_THREADS=1
{ ./Config.pl -install -compiler=gfortran -noamrex > /home/kosaka/build_log_config.txt 2>&1; echo CONFIG_EXIT=$?; }
ls -la bin/SWMF.exe Makefile.def
grep -c COMP Makefile.def
cat Makefile.def | grep -E 'COMPLIST|COMPONENTS' | head -5
