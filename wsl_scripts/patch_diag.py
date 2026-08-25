p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
# diagnostic edits: disable IM in session 3, shorten init
subs = [
    ('IM\t\t\tNameComp\nT\t\t\tUseComp', 'IM\t\t\tNameComp\nF\t\t\tUseComp'),
    ('700\t\t\tMaxIter', '50\t\t\tMaxIter'),
    ('1500\t\t\tMaxIter', '50\t\t\tMaxIter'),
]
for a, b in subs:
    n = t.count(a)
    t = t.replace(a, b)
    print(f'{a!r} -> {b!r} ({n}x)')
open(p, 'w').write(t)