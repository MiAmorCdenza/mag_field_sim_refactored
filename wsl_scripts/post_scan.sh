#!/bin/bash
# Usage: post_scan.sh TAG   (run inside run_magfield)
# Converts 3D idl -> tec, extracts npz to swmf_output, cleans intermediates,
# archives the raw AMR master with the condition tag.
set -e
TAG=$1
cd /home/kosaka/swmf_fresh/run_magfield/GM
# convert 3D
./pIDL -f=tec "IO2/3d__mhd_3_n00000600" > /dev/null 2>&1
# extract
/home/kosaka/mag_field_sim/.venv/bin/python3 \
  /mnt/c/Users/Admin/Documents/trae_projects/mag_field_sim/wsl_scripts/extract_tec16.py \
  IO2/3d__mhd_3_n00000600.dat /home/kosaka/swmf_output --tag "$TAG"
# cleanup: delete per-PE idl/tree/info intermediates (keep 2D .dat + logs)
rm -f IO2/3d__mhd_3_n00000600_pe*.idl IO2/3d__mhd_3_n00000600.tree IO2/3d__mhd_3_n00000600.info
# archive raw AMR master on ext4
mkdir -p /home/kosaka/swmf_archive
mv IO2/3d__mhd_3_n00000600.dat /home/kosaka/swmf_archive/3d__mhd_${TAG}.dat
# copy final products to Windows workspace
DEST=/mnt/c/Users/Admin/Documents/trae_projects/mag_field_sim/data_swmf
cp /home/kosaka/swmf_output/${TAG}_*.npz $DEST/
cp IO2/y=0_mhd_1_n00000600.dat $DEST/y0_${TAG}.dat
cp IO2/z=0_mhd_2_n00000600.dat $DEST/z0_${TAG}.dat
echo "POST_SCAN_DONE $TAG"
du -sh /home/kosaka/swmf_output $DEST
