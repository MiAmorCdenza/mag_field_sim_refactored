p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
# revert limits to standard
subs = [
    ('1200\t\t\tMaxBlock', '5000\t\t\tMaxBlock'),
    ('500\t\t\tMaxIter', '700\t\t\tMaxIter'),
    ('1000\t\t\tMaxIter', '1500\t\t\tMaxIter'),
]
for a, b in subs:
    n = t.count(a)
    t = t.replace(a, b)
    print(f'{a!r} -> {b!r} ({n}x)')
# add SAVERESTART at end of session 2 GM block (before its #END_COMP GM)
anchor = ('0.6\t\t\tCflExpl\n'
          '\n'
          '#END_COMP GM ---')
repl = ('0.6\t\t\tCflExpl\n'
        '\n'
        '#SAVERESTART\n'
        'T\t\t\tDoSaveRestart\n'
        '-1\t\t\tDnSaveRestart\n'
        '-1.\t\t\tDtSaveRestart\n'
        '\n'
        '#END_COMP GM ---')
n = t.count(anchor)
t = t.replace(anchor, repl, 1)
print('SAVERESTART added to session2 GM:', n, 'anchor found')
open(p, 'w').write(t)