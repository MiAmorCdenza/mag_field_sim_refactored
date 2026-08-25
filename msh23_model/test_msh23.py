"""Test MSH23 model at diagnostic points and compare with current models."""
import subprocess, os

os.chdir(os.path.dirname(__file__))

tests = [
    ('Subsolar (psi=0)',     '12.0 0.0 0.0 0.0 2.0 -4.0 4.0 -2.0'),
    ('Subsolar (psi=0.5)',   '12.0 0.0 0.0 0.5 2.0 -4.0 4.0 -2.0'),
    ('Dusk flank (Y=+12)',   '0.0 12.0 0.0 0.3 2.0 -4.0 4.0 -2.0'),
    ('Dawn flank (Y=-12)',   '0.0 -12.0 0.0 0.3 2.0 -4.0 4.0 -2.0'),
    ('Low Pdyn (1 nPa)',     '10.0 0.0 0.0 0.3 1.0 -4.0 4.0 -2.0'),
    ('High Pdyn (6 nPa)',    '10.0 0.0 0.0 0.3 6.0 -4.0 4.0 -2.0'),
    ('IMF Bz south (-5)',    '-5.0 10.0 3.0 0.3 2.0 -2.0 0.0 -5.0'),
    ('IMF Bz north (+5)',    '-5.0 10.0 3.0 0.3 2.0 -2.0 0.0 5.0'),
]

input_str = '\n'.join(t[1] for t in tests)
p = subprocess.run(['./msh23_test.exe'], input=input_str, capture_output=True, text=True)
lines = p.stdout.strip().split('\n')

id_map = {0: 'MSH', 1: 'SW', 2: 'MP'}
print('=' * 70)
print(f'{"MSH23 Model Diagnostics":^70}')
print('=' * 70)
for (label, _), line in zip(tests, lines):
    parts = line.split()
    ids = int(parts[0])
    bx = float(parts[1])
    by = float(parts[2])
    bz = float(parts[3])
    print(f'{label:25s} ID={id_map.get(ids,"?")}  B=({bx:8.2f} {by:8.2f} {bz:8.2f}) nT')
