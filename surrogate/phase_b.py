import sys
sys.path.insert(0, 'surrogate')
from run_phaseA import run_variant
res = run_variant('b_mlp_B_divpen', ['data_swmf/swmf_n600_inner_0.25Re.npz', 'data_swmf/swmf_n600_full_1Re.npz'])
print('PHASE_B_DONE', res['all'])
