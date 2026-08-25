#!/bin/bash
set -x
cd /home/kosaka/swmf_fresh
# Link large data dirs from existing SWMF_data checkout
if [ ! -e GM/BATSRUS/data ] && [ -d /home/kosaka/SWMF_data/GM/BATSRUS/data ]; then
  ln -s /home/kosaka/SWMF_data/GM/BATSRUS/data GM/BATSRUS/data && echo LINK_GM_DATA_OK
fi
for c in IM/RCM2 IM/CIMI IM/HEIDI PT/MITTENS PW/PWOM UA/MGITM; do
  if [ ! -e $c/data ] && [ -d /home/kosaka/SWMF_data/$c/data ]; then
    ln -s /home/kosaka/SWMF_data/$c/data $c/data && echo LINK_OK_$c
  fi
done
# Install configuration
./Config.pl -install -compiler=gfortran -noamrex 2>&1 | tail -12
echo CONFIG_DONE
# Build SWMF executable + IDL postprocessor
make -j 32 SWMF PIDL 2>&1 | tail -25
echo BUILD_DONE
ls -la SWMF.exe bin/SWMF.exe util/IDLPostProc/IDLPostProc.exe 2>/dev/null | head -5
