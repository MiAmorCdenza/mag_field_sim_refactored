p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
# Session 2 SAVEPLOT block (the one with nPlotFile 2 + '5 min'):
#   add 3d MHD idl output triggered by step number 1500 (end of session 2)
old = ('#SAVEPLOT\n'
       '2\t\t\tnPlotFile\n'
       'y=0 MHD idl\t\tStringPlot\n'
       '-1\t\t\tDnSavePlot\n'
       '5 min\t\t\tDtSavePlot\n'
       '-1.0\t\t\tDxSavePlot\n'
       'z=0 MHD idl\t\tStringPlot\n'
       '-1\t\t\tDnSavePlot\n'
       '5 min\t\t\tDtSavePlot\n'
       '-1.0\t\t\tDxSavePlot\n')
new = ('#SAVEPLOT\n'
       '3\t\t\tnPlotFile\n'
       'y=0 MHD idl\t\tStringPlot\n'
       '-1\t\t\tDnSavePlot\n'
       '5 min\t\t\tDtSavePlot\n'
       '-1.0\t\t\tDxSavePlot\n'
       'z=0 MHD idl\t\tStringPlot\n'
       '-1\t\t\tDnSavePlot\n'
       '5 min\t\t\tDtSavePlot\n'
       '-1.0\t\t\tDxSavePlot\n'
       '3d MHD idl\t\tStringPlot\n'
       '1500\t\t\tDnSavePlot\n'
       '-1.0\t\t\tDtSavePlot\n'
       '-1.0\t\t\tDxSavePlot\n')
import re
# find the FIRST session-2-style SAVEPLOT (2 plots, 5 min) — session 2's block
n = t.count(old)
t = t.replace(old, new, 1)
print(f'session2 SAVEPLOT patched ({n} occurrences matched, replaced 1)')
open(p, 'w').write(t)
# verify: show all SAVEPLOT blocks with their trigger lines
for m in re.finditer(r'#SAVEPLOT\n(\d+)\t+nPlotFile\n([\s\S]{0,420}?)(?=#END|#BEGIN|#SAVERESTART)', t):
    print('--- block nPlotFile=', m.group(1))
    for line in m.group(2).split(chr(10))[:16]: print('   ', line)