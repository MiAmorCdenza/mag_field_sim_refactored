#!/bin/bash
set -x
cd /home/kosaka/swmf_fresh
# Create run directory
make rundir RUNDIR=/home/kosaka/swmf_fresh/run_magfield > /home/kosaka/rundir_log.txt 2>&1
echo RUNDIR_EXIT=$?
cd /home/kosaka/swmf_fresh/run_magfield
# Copy SWPC driver/input files
cp ../Param/SWPC/PARAM.in_SWPC_simple_init PARAM.in
cp ../Param/SWPC/IMF.dat ../Param/SWPC/SATELLITES.in ../Param/SWPC/magin_GEM.dat ../Param/SWPC/INTERPOLATE.in .
cp ../Param/SWPC/sat01.dat . 2>/dev/null
# Add 3D tec output
python3 /mnt/c/Users/Admin/Documents/trae_projects/mag_field_sim/wsl_scripts/adapt_param.py PARAM.in PARAM.in
echo '=== SAVEPLOT in time-accurate section ==='
grep -A 14 '#SAVEPLOT' PARAM.in | tail -16
ls -la
