import sys
sys.path.insert(0, 'surrogate')
from run_phaseA import run_variant
res = run_variant('c_mlp_A', ['data_swmf/swmf_n600_inner_0.25Re.npz', 'data_swmf/swmf_n600_full_1Re.npz'],
                  n_points=120000, n_train=100000, epochs=30)
print('PHASE_C_DONE', res['all'])
