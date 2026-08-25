p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
n = t.count('3d MHD real4')
t = t.replace('3d MHD real4', '3d MHD idl')
open(p, 'w').write(t)
print(f'3d MHD real4 -> idl ({n}x)')