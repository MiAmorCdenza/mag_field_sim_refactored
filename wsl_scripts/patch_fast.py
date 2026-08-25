p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
t = t.replace('700\t\t\tMaxIter', '50\t\t\tMaxIter', 1)
t = t.replace('1500\t\t\tMaxIter', '50\t\t\tMaxIter', 1)
open(p, 'w').write(t)
import re; print([m.group(0) for m in re.finditer(r'\d+\t+MaxIter', t)])