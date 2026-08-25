import re
p = '/home/kosaka/swmf_fresh/run_magfield/PARAM.in'
t = open(p).read()
# find all '#COMPONENT ... IM ... UseComp' blocks in order
blocks = list(re.finditer(r'#COMPONENT\nIM\t+NameComp\n([TF])\t+UseComp', t))
print('found', len(blocks), 'IM component blocks')
for m in blocks:
    print('  at offset', m.start(), '->', m.group(1))
# assign: first block (session1) -> F, last block (session3) -> T
t = t[:blocks[0].start(1)] + 'F' + t[blocks[0].end(1):]
blocks = list(re.finditer(r'#COMPONENT\nIM\t+NameComp\n([TF])\t+UseComp', t))
t = t[:blocks[-1].start(1)] + 'T' + t[blocks[-1].end(1):]
open(p, 'w').write(t)
blocks = list(re.finditer(r'#COMPONENT\nIM\t+NameComp\n([TF])\t+UseComp', t))
print('after fix:', [m.group(1) for m in blocks])