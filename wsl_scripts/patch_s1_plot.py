p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
old = ('#SAVEPLOT\n'
       '2\t\t\tnPlotFile\n'
       'y=0 MHD idl\t\tStringPlot\n'
       '2500\t\t\tDnSavePlot\n'
       '-1.\t\t\tDtSavePlot\n'
       '-1.\t\t\tDxSavePlot\n'
       'z=0 MHD idl\t\tStringPlot\n'
       '2500\t\t\tDnSavePlot\n'
       '-1.\t\t\tDtSavePlot\n'
       '-1.\t\t\tDxSavePlot\n')
new = ('#SAVEPLOT\n'
       '3\t\t\tnPlotFile\n'
       'y=0 MHD idl\t\tStringPlot\n'
       '1500\t\t\tDnSavePlot\n'
       '-1.\t\t\tDtSavePlot\n'
       '-1.\t\t\tDxSavePlot\n'
       'z=0 MHD idl\t\tStringPlot\n'
       '1500\t\t\tDnSavePlot\n'
       '-1.\t\t\tDtSavePlot\n'
       '-1.\t\t\tDxSavePlot\n'
       '3d MHD idl\t\tStringPlot\n'
       '1500\t\t\tDnSavePlot\n'
       '-1.\t\t\tDtSavePlot\n'
       '-1.\t\t\tDxSavePlot\n')
n = t.count(old)
t = t.replace(old, new, 1)
print(f'matched {n}, replaced 1')
open(p, 'w').write(t)
import re
i = t.find('3d MHD idl')
print(t[i-180:i+120])