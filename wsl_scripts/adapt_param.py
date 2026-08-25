#!/usr/bin/env python3
"""Adapt SWPC PARAM.in: add 3D tec output via exact regex substitution."""
import sys, re
src, dst = sys.argv[1], sys.argv[2]
with open(src, encoding='utf-8', errors='replace') as f:
    text = f.read()

old_block = ('#SAVEPLOT\n'
             '2\t\t\tnPlotFile\n'
             'y=0 MHD idl\t\tStringPlot\n'
             '-1\t\t\tDnSavePlot\n'
             '5 min\t\t\tDtSavePlot\n'
             '-1.0\t\t\tDxSavePlot\n'
             'z=0 MHD idl\t\tStringPlot\n'
             '-1\t\t\tDnSavePlot\n'
             '5 min\t\t\tDtSavePlot\n'
             '-1.0\t\t\tDxSavePlot\n')
new_block = ('#SAVEPLOT\n'
             '3\t\t\tnPlotFile\n'
             'y=0 MHD idl\t\tStringPlot\n'
             '-1\t\t\tDnSavePlot\n'
             '5 min\t\t\tDtSavePlot\n'
             '-1.0\t\t\tDxSavePlot\n'
             'z=0 MHD idl\t\tStringPlot\n'
             '-1\t\t\tDnSavePlot\n'
             '5 min\t\t\tDtSavePlot\n'
             '-1.0\t\t\tDxSavePlot\n'
             '3d MHD tec\t\tStringPlot\n'
             '-1\t\t\tDnSavePlot\n'
             '20 min\t\t\tDtSavePlot\n'
             '-1.0\t\t\tDxSavePlot\n')

text, n = re.subn(re.escape(old_block), new_block.replace('\\', '\\\\'), text, count=1)
if n != 1:
    print(f'ERROR: matched {n} blocks (expected 1)'); sys.exit(1)
with open(dst, 'w') as f:
    f.write(text)
print('OK: exact replacement done, n=1')