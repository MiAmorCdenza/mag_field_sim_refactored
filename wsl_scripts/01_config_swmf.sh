#!/bin/bash
set -x
cd /home/kosaka/swmf_fresh
# Check amrex option
./Config.pl -help 2>&1 | grep -i -A1 'amrex\|noamrex' | head -8
# Install config (gfortran CPU build - proven path)
./Config.pl -install -compiler=gfortran -noamrex 2>&1 | tail -15
echo CONFIG_DONE
