p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
t = t.replace('700\t\t\tMaxIter', '300\t\t\tMaxIter', 1)
t = t.replace('1500\t\t\tMaxIter', '600\t\t\tMaxIter', 1)
n = t.count('1500\t\t\tDnSavePlot')
t = t.replace('1500\t\t\tDnSavePlot', '300\t\t\tDnSavePlot')
open(p, 'w').write(t)
import re
print([m.group(0) for m in re.finditer(r'\d+\t+MaxIter', t)])
print('DnSavePlot occurrences patched:', n)