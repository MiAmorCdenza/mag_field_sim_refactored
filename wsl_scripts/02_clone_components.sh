#!/bin/bash
set -x
cd /home/kosaka/swmf_fresh
./Config.pl -clone 2>&1 | tail -40
echo '=== POST-CLONE STATE ==='
ls GM/BATSRUS/ | tr '\n' ' '; echo
ls IM/ | tr '\n' ' '; echo
ls IE/ | tr '\n' ' '; echo
du -sh GM/BATSRUS IM IE 2>/dev/null
