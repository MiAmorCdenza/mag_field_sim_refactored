p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
subs = [
    ('IM\t\t\tNameComp\nF\t\t\tUseComp', 'IM\t\t\tNameComp\nT\t\t\tUseComp'),
    ('50\t\t\tMaxIter', '700\t\t\tMaxIter'),  # first occurrence -> session1
    ('50\t\t\tMaxIter', '1500\t\t\tMaxIter'), # second -> session2
]
for a, b in subs:
    n = t.count(a)
    t = t.replace(a, b, 1)
    print(f'{a!r} -> {b!r} ({n}x)')
open(p, 'w').write(t)
print('---verify---')
import re
for m in re.finditer(r'(\d+)\t+MaxIter', t): print(m.group(0))
for m in re.finditer(r'IM\t+NameComp\n[TF]\t+UseComp', t): print('IM:', m.group(0).split(chr(10))[1])