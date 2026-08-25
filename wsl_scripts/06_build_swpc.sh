#!/bin/bash
cd /home/kosaka/swmf_fresh
export OMP_NUM_THREADS=1
./Config.pl -default > /home/kosaka/build_log_config2.txt 2>&1
./Config.pl -v=Empty,GM/BATSRUS,IE/Ridley_serial,IM/RCM2 >> /home/kosaka/build_log_config2.txt 2>&1
./Config.pl -o=GM:u=Default,e=Mhd,ng=2,g=8,8,8,IE:g=181,361 >> /home/kosaka/build_log_config2.txt 2>&1
echo CONFIG2_EXIT=$?
grep -E 'GM_VERSION|IE_VERSION|IM_VERSION' Makefile.def
make -j 32 SWMF PIDL INTERPOLATE > /home/kosaka/build_log_make2.txt 2>&1
echo MAKE2_EXIT=$?
tail -6 /home/kosaka/build_log_make2.txt
ls -la bin/SWMF.exe
