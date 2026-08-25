p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
# swap 3d tec -> 3d real4
a = ('3d MHD tec\t\tStringPlot\n-1\t\t\tDnSavePlot\n20 min\t\t\tDtSavePlot\n-1.0\t\t\tDxSavePlot\n')
b = ('3d MHD real4\t\tStringPlot\n-1\t\t\tDnSavePlot\n20 min\t\t\tDtSavePlot\n-1.0\t\t\tDxSavePlot\n')
n = t.count(a)
t = t.replace(a, b)
print(f'3d tec -> real4 ({n}x)')
# restore MaxIter
t = t.replace('50\t\t\tMaxIter', '700\t\t\tMaxIter', 1)
t = t.replace('50\t\t\tMaxIter', '1500\t\t\tMaxIter', 1)
open(p, 'w').write(t)
import re; print([m.group(0) for m in re.finditer(r'\d+\t+MaxIter', t)])
print([m.group(0) for m in re.finditer(r'3d MHD \w+', t)])