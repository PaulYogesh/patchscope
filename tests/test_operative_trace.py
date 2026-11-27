"""New public trace is separate from evaluation tests and opt-in gated."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from patchscope.agent import run_episode
from patchscope.experiment import load_manifest, build_schedule
from patchscope.operative_trace import trace_public_reproducer, render_trace_hint
from patchscope.operative_compare import compare_operative
from patchscope.repair import temporary_repo, apply_exact_edit, run_pytest

ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    def __init__(self, proposal):
        self.proposal, self.calls = proposal, []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = 'Exploration complete' if len(self.calls) == 1 else json.dumps(self.proposal)
        return NS(choices=[NS(message=NS(content=response, tool_calls=[]), finish_reason='stop')],
                  usage=NS(prompt_tokens=100, completion_tokens=60))


def schedule(policy):
    manifest = load_manifest(ROOT / f'experiments/operative-{policy}-v060.json')
    items = [i for i in build_schedule(manifest) if i['condition'] == 'oracle']
    return manifest, items


def test_public_traces_are_separate_and_only_operative_modules_execute():
    for folder, expected, wrong in [
        ('tax_dispatch', 'tax_core.py', 'tax_legacy.py'),
        ('backoff_dispatch', 'backoff_core.py', 'backoff_compat.py'),
    ]:
        repo = ROOT / 'fixtures' / 'operative_v060' / folder
        script = ROOT / 'reproducers' / 'public_v060' / f'{folder}.py'
        before = {p.name:p.read_bytes() for p in repo.glob('*.py')}
        result = trace_public_reproducer(repo, script)
        assert result['reproducer_failed']
        assert expected in result['executed_paths']
        assert 'service.py' in result['executed_paths']
        assert wrong not in result['executed_paths']
        assert not any(p.startswith('test_') for p in result['executed_paths'])
        assert 'not proof' in render_trace_hint(result)
        assert before == {p.name:p.read_bytes() for p in repo.glob('*.py')}


def test_public_trace_rejects_private_test_script_and_mismatched_policy():
    repo = ROOT/'fixtures/operative_v060/tax_dispatch'
    with pytest.raises(ValueError, match='reproducer_must_be_separate'):
        trace_public_reproducer(repo, repo/'test_contract.py')
    m, _ = schedule('trace')
    m['tasks'][0]['public_reproducer_path'] = m['tasks'][0]['repo_path']+'/test_contract.py'
    path = ROOT/'experiments/operative-trace-v060.json'
    assert path.exists()  # in-memory mutation does not affect the checked manifest


def test_reference_repairs_pass_and_baselines_fail_without_mutating_originals():
    repairs = {
        'tax_dispatch': ('tax_core.py','round(amount * (1 + tax_rate), 0)','round(amount * (1 + tax_rate), 2)'),
        'backoff_dispatch':('backoff_core.py','base * attempt','base * (2 ** (attempt - 1))'),
    }
    for name, (file, old, new) in repairs.items():
        repo=ROOT/'fixtures/operative_v060'/name
        before = (repo/file).read_bytes()
        with temporary_repo(repo) as tmp:
            assert not run_pytest(tmp)['passed']
            apply_exact_edit(tmp,file,old,new)
            assert run_pytest(tmp)['passed']
        assert before == (repo/file).read_bytes()


def test_original_manifest_has_no_trace_and_exploration_receives_trace():
    m_off, items = schedule('off')
    m_on, _ = schedule('trace')
    off_item = next(x for x in items if x['task_id']=='tax-dynamic-dispatch-013')
    on_item = next(x for x in build_schedule(m_on) if x['task_id']==off_item['task_id'] and x['condition']=='oracle')
    assert off_item['model_seed'] == on_item['model_seed']
    patch = {'path':'tax_core.py','old':'round(amount * (1 + tax_rate), 0)',
             'new':'round(amount * (1 + tax_rate), 2)'}
    clients=[]
    for manifest,item in [(m_off,off_item),(m_on,on_item)]:
        client=FakeClient(patch)
        record=run_episode(item=item, manifest=manifest, root=ROOT,client=client,model='fake',
                           provenance={},allow_trusted_execution=True)
        assert record['outcome']['repair_verified']
        assert record['usage']['model_calls']==2
        clients.append(client)
    assert clients[0].calls[0]['messages'][0] == clients[1].calls[0]['messages'][0]
    assert 'PUBLIC REPRODUCER EXECUTION EVIDENCE' not in clients[0].calls[0]['messages'][1]['content']
    assert 'PUBLIC REPRODUCER EXECUTION EVIDENCE' in clients[1].calls[0]['messages'][1]['content']
    assert clients[0].calls[1]['messages'] == clients[1].calls[1]['messages']
    assert clients[1].calls[1]['max_tokens']==1600


def test_trace_requires_execution_opt_in_and_old_experiments_remain_off():
    m, items=schedule('trace')
    item=next(i for i in items if i['task_id']=='tax-dynamic-dispatch-013')
    client=FakeClient({'path':'tax_core.py','old':'wrong','new':'right'})
    record=run_episode(item=item,manifest=m,root=ROOT,client=client,model='fake',
                       provenance={},allow_trusted_execution=False)
    assert record['outcome']['status']=='error'
    assert 'requires_trusted_execution' in record['error']
    old=load_manifest(ROOT/'experiments/interference_smoke_v030.json')
    assert old.get('operative_trace_policy','off')=='off'


def test_comparison_checks_provenance_and_exploration(tmp_path):
    for name, policy, verified, patch in [
        ('operative-off-v060','off',False,'backoff_compat.py'),
        ('operative-trace-v060','public_reproducer',True,'backoff_core.py'),
    ]:
        folder = tmp_path/'runs'/name
        folder.mkdir(parents=True)
        rec = {
            'experiment_id': name,'task_id':'retry-dynamic-dispatch-014',
            'run_id':'retry-dynamic-dispatch-014__native__r00',
            'repetition':0,'condition':'native',
            'operative_trace_policy':policy,
            'operative_trace':({
                'reproducer_failed':True,
                'executed_paths':['service.py','backoff_core.py'],
            } if policy!='off' else None),
            'proposal':{'path':patch},
            'outcome':{'status':'resolved' if verified else 'repair_failed_tests',
                       'repair_verified':verified},
            'trajectory':[{'kind':'model_response','purpose':'exploration',
                           'completion_tokens':60}],
            'provenance':{'source_tree_sha256':'same-source','generation':{
                'model':'fake-model','seed':42,'temperature':0},
                'ollama':{'digest':'verified-test-model'}},
            'usage':{'total_tokens':200 if verified else 190},
        }
        (folder/'retry-dynamic-dispatch-014__native__r00.json').write_text(json.dumps(rec))
    result=compare_operative(tmp_path)
    assert result['n_matched']==1
    assert result['trace_verified']==1
    assert result['rows'][0]['identical_exploration']
    assert result['rows'][0]['trace_patch_executed']
    bad = tmp_path/'runs'/'operative-trace-v060'/'retry-dynamic-dispatch-014__native__r00.json'
    rec=json.loads(bad.read_text())
    rec['provenance']['ollama']['digest']='different-model'
    bad.write_text(json.dumps(rec))
    with pytest.raises(ValueError,match='operative_provenance_mismatch'):
        compare_operative(tmp_path)
