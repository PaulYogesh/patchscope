import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from patchscope.source_map import source_reference_map
from patchscope.agent import run_episode
from patchscope.experiment import load_manifest, build_schedule

ROOT=Path(__file__).resolve().parents[1]


def test_static_source_map_shows_only_non_test_imports():
    repo=ROOT/'fixtures/benchmark_v040/decoy/owner-access-009'
    row=source_reference_map(repo,policy='imports')
    assert 'service.py -> policy.py' in row['text']
    assert 'test_contract.py' not in row['text']
    assert 'oracle' not in row['text'].lower()
    assert row['static_edges']>0


def test_inventory_has_no_edges_but_same_file_list():
    repo=ROOT/'fixtures/benchmark_v040/decoy/owner-access-009'
    a=source_reference_map(repo,policy='inventory')
    b=source_reference_map(repo,policy='imports')
    assert 'policy_compat.py' in a['text'] and 'policy_compat.py' in b['text']
    assert 'service.py -> policy.py' not in a['text']
    assert a['files']==b['files']


def test_no_static_imports_does_not_flag_disuse():
    repo=ROOT/'fixtures/interference_mini_repo'
    row=source_reference_map(repo,policy='imports')
    assert row['static_edges']==0
    assert 'inconclusive' in row['text']


def test_map_limit_bad_policy_and_determinism():
    repo=ROOT/'fixtures/benchmark_v040/decoy/owner-access-009'
    assert source_reference_map(repo,policy='imports')==source_reference_map(repo,policy='imports')
    with pytest.raises(ValueError):source_reference_map(repo,policy='untrusted')
    with pytest.raises(ValueError):source_reference_map(repo,policy='imports',max_chars=5)


def test_legacy_manifest_preserves_unmodified_policy():
    manifest=load_manifest(ROOT/'experiments/interference_smoke_v030.json')
    assert manifest.get('evidence_policy','off')=='off'


def test_new_manifests_and_seeds_match_baseline():
    base=load_manifest(ROOT/'experiments/interference_smoke_v030.json')
    for mode in ['inventory','imports']:
        new=load_manifest(ROOT/f'experiments/evidence_{mode}_v050.json')
        assert new['evidence_policy']==mode
        assert [r['model_seed'] for r in build_schedule(base)] == [r['model_seed'] for r in build_schedule(new)]


class FakeClient:
    def __init__(self,patch):
        self.calls=[]
        self.responses=[(None,[('read_file',{'path':'calculator.py'})]),('Enough evidence',[]),(json.dumps(patch),[])]
        self.chat=NS(completions=NS(create=self.create))
    def create(self,**kwargs):
        self.calls.append(kwargs)
        content,tools=self.responses.pop(0)
        calls=[NS(id='x',type='function',function=NS(name=n,arguments=json.dumps(a))) for n,a in tools]
        return NS(choices=[NS(message=NS(content=content,tool_calls=calls),finish_reason='stop')],usage=NS(prompt_tokens=130,completion_tokens=40))


def test_evidence_injected_after_exploration_only():
    patch={'path':'calculator.py','old':'return sum(values) // len(values)','new':'return sum(values) / len(values)'}
    prepared=[]
    for policy in ('off','inventory','imports'):
        manifest=load_manifest(ROOT/'experiments/interference_smoke_v030.json')
        manifest['evidence_policy']=policy
        item=next(row for row in build_schedule(manifest) if row['task_id']=='mini-average-001' and row['condition']=='native')
        client=FakeClient(patch)
        record=run_episode(item=item,manifest=manifest,root=ROOT,client=client,model='fake',provenance={})
        assert record['proposal_evidence']['policy']==policy
        assert record['outcome']['status']=='proposal_requires_explicit_verification_opt_in'
        prepared.append(client.calls)
    for idx in (0,1):
        assert prepared[0][idx]['messages']==prepared[1][idx]['messages']==prepared[2][idx]['messages']
    assert prepared[0][2]['messages']!=prepared[1][2]['messages']
    assert prepared[1][2]['messages']!=prepared[2][2]['messages']


def test_benchmark_control_manifests_preserve_task_seeds():
    baseline=load_manifest(ROOT/'experiments/benchmark-decoy-v040.json')
    for policy in ('inventory','imports'):
        new=load_manifest(ROOT/f'experiments/evidence_benchmark_{policy}_v050.json')
        assert new['evidence_policy']==policy
        assert [r['model_seed'] for r in build_schedule(new)]==[r['model_seed'] for r in build_schedule(baseline)]
