import pytest

from patchscope.evidence_policy_compare import compare_policies,render_comparison


def fake(policy, verified, file='decoy.py'):
    return {'task_id':'t','repetition':0,'condition':'native',
            'provenance':{'generation':{'seed':44,'model':'qwen'},'ollama':{'digest':'abc'}},
            'budgets':{'max_steps':6,'source_map_char_budget':1400 if policy!='off' else 0},
            'proposal_evidence':{'policy':policy,'chars':12,'static_edges':1},
            'trajectory':[{'kind':'tool_call','name':'read_file','arguments':{'path':'a.py'},'event_index':1}],
            'observed_paths':['a.py'],
            'outcome':{'status':'resolved' if verified else 'repair_failed_tests','repair_verified':verified},
            'proposal':{'path':file},'usage':{'total_tokens':1200}}


def test_match_and_rejection():
    group={k:{('t',0):fake(p, k=='imports')} for k,p in [('baseline','off'),('inventory','inventory'),('imports','imports')]}
    comp=compare_policies(group)
    assert comp['n_matching_exploration']==1
    assert '| `t` |' in render_comparison(comp)
    group['inventory'][('t',0)]['observed_paths']=['different.py']
    assert compare_policies(group)['n_matching_exploration']==0
    group['inventory'][('t',0)]['provenance']['generation']['seed']=99
    with pytest.raises(ValueError,match='mismatch'):
        compare_policies(group)


def test_missing_arm_rejected():
    with pytest.raises(ValueError):compare_policies({'baseline':{},'inventory':{},'imports':{}})
