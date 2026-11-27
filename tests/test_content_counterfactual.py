"""Three-way native matched control with no LLM/network calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from patchscope.content_counterfactual import (
    compare_content_variants, validate_content_variants,
)
from patchscope.experiment import build_schedule, load_manifest
from patchscope.repair import apply_exact_edit, run_pytest, temporary_repo
from scripts.compare_decoy_content import render

ROOT = Path(__file__).resolve().parents[1]


def manifests():
    return tuple(load_manifest(ROOT / 'experiments' / name)
                 for name in ('decoy_free_native_v031.json',
                              'same_name_neutral_v032.json',
                              'interference_smoke_v030.json'))


def record(experiment_id: str, task_id: str, seed: int, *, patch: str, verified: bool):
    return {
        'experiment_id': experiment_id, 'task_id': task_id,
        'condition': 'native', 'repetition': 0,
        'run_id': f'{task_id}__native__r00',
        'provenance': {
            'generation': {'model': 'qwen3.5:9b', 'temperature': 0,
                           'seed': seed, 'tool_policy': 'native_required'},
            'prompt_version': 'v023', 'tool_schema_sha256': 'h',
            'ollama': {'digest': 'digest'},
        },
        'budgets': {'max_patch_completion_tokens_per_call': 1400},
        'trajectory': [{'kind': 'patch_proposal', 'path': patch, 'old': 'x', 'new': 'y'}],
        'proposal': {'path': patch, 'old': 'x', 'new': 'y'},
        'outcome': {'status': 'resolved' if verified else 'repair_failed_tests',
                    'repair_verified': verified},
        'usage': {'total_tokens': 2700},
        'intervention': {'sources': []},
    }


def sample():
    ms = manifests()
    seeds = {item['task_id']: item['model_seed'] for item in build_schedule(ms[0])
             if item['condition'] == 'native'}
    groups = []
    for m in ms:
        group = [record(m['experiment_id'], t['task_id'], seeds[t['task_id']],
                        patch=t['oracle']['paths'][0], verified=True)
                 for t in m['tasks']]
        groups.append(group)
    return (*ms, *groups)


def test_real_fixture_parity_and_same_added_file_path():
    clean, neutral, decoy = manifests()
    r = validate_content_variants(clean, neutral, decoy, ROOT)
    assert len(r) == 4
    assert {x['extra_path'] for x in r} == {
        'average_utils.py', 'bounds_compat.py', 'slugify.py', 'pricing_compat.py',
    }
    assert all(abs(x['neutral_minus_decoy_bytes']) / x['decoy_bytes'] <= .10 for x in r)
    assert all(x['neutral_sha256'] != x['decoy_sha256'] for x in r)


def test_native_model_seeds_equal_across_three_conditions():
    schedules = [
        {(r['task_id'], r['repetition']): r['model_seed'] for r in build_schedule(m)
         if r['condition'] == 'native'}
        for m in manifests()
    ]
    assert schedules[0] == schedules[1] == schedules[2]
    assert len(schedules[0]) == 4


def test_counterfactual_success_loss_and_report():
    a, b, c, ar, br, cr = sample()
    cr[0]['outcome']['repair_verified'] = False
    cr[0]['outcome']['status'] = 'repair_failed_tests'
    cr[0]['proposal']['path'] = c['tasks'][0]['misleading_pool'][0]
    cr[0]['trajectory'][0]['path'] = cr[0]['proposal']['path']
    r = compare_content_variants(ar, br, cr, a, b, c, ROOT)
    assert r['n_distinct_tasks'] == r['n_matched_episodes'] == 4
    assert r['summary']['clean_verified'] == 4
    assert r['summary']['neutral_verified'] == 4
    assert r['summary']['decoy_verified'] == 3
    assert r['summary']['lost_neutral_to_decoy'] == 1
    assert r['summary']['decoy_extra_path_edits'] == 1
    md = render(r)
    assert 'same-filename' in md
    assert 'repository composition' in md
    assert 'average_utils.py' in md


def test_rejects_missing_episode():
    a, b, c, ar, br, cr = sample()
    with pytest.raises(ValueError, match='Incomplete neutral'):
        compare_content_variants(ar, br[:-1], cr, a, b, c, ROOT)


def test_rejects_changed_generation_seed():
    a, b, c, ar, br, cr = sample()
    br[0]['provenance']['generation']['seed'] += 1
    with pytest.raises(ValueError, match='provenance differs'):
        compare_content_variants(ar, br, cr, a, b, c, ROOT)


def test_rejects_unverified_episode():
    a, b, c, ar, br, cr = sample()
    cr[0]['outcome']['status'] = 'proposal_requires_explicit_verification_opt_in'
    with pytest.raises(ValueError, match='Unverified execution'):
        compare_content_variants(ar, br, cr, a, b, c, ROOT)


def test_rejects_content_too_different(tmp_path):
    import shutil
    clean, neutral, decoy = manifests()
    for m in (clean, neutral, decoy):
        for t in m['tasks']:
            original = ROOT / t['repo_path']
            target = tmp_path / original.name
            if not target.exists():
                shutil.copytree(original, target)
            t['repo_path'] = original.name
    (tmp_path / 'content_control_mini_repo' / 'average_utils.py').write_text('x = 1\n')
    with pytest.raises(ValueError, match='lengths differ >10%'):
        validate_content_variants(clean, neutral, decoy, tmp_path)


def test_rejects_nondecoy_source_modification(tmp_path):
    import shutil
    clean, neutral, decoy = manifests()
    for m in (clean, neutral, decoy):
        for t in m['tasks']:
            original = ROOT / t['repo_path']
            target = tmp_path / original.name
            if not target.exists():
                shutil.copytree(original, target)
            t['repo_path'] = original.name
    (tmp_path / 'content_control_mini_repo' / 'calculator.py').write_text('x=1\n')
    with pytest.raises(ValueError, match='non-decoy fixture difference'):
        validate_content_variants(clean, neutral, decoy, tmp_path)


def test_rejects_same_function_semantics(tmp_path):
    import shutil
    clean, neutral, decoy = manifests()
    for m in (clean, neutral, decoy):
        for t in m['tasks']:
            original = ROOT / t['repo_path']
            target = tmp_path / original.name
            if not target.exists():
                shutil.copytree(original, target)
            t['repo_path'] = original.name
    # match byte count to bypass length matching, but reuse decoy name.
    dst = tmp_path / 'content_control_mini_repo' / 'average_utils.py'
    decoy_file = tmp_path / 'interference_mini_repo' / 'average_utils.py'
    data = decoy_file.read_text().replace('def average(', 'def average(')
    dst.write_text(data)
    with pytest.raises(ValueError, match='expected only changed decoy content'):
        validate_content_variants(clean, neutral, decoy, tmp_path)


@pytest.mark.parametrize('task', manifests()[1]['tasks'])
def test_neutral_repository_still_has_same_bug_and_reference_fix(task):
    repo = ROOT / task['repo_path']
    fixes = {
        'mini-average-001': ('calculator.py', 'return sum(values) // len(values)', 'return sum(values) / len(values)'),
        'mini-clamp-002': ('limits.py', 'return max(upper, min(lower, value))', 'return max(lower, min(upper, value))'),
        'mini-slug-003': ('text_ops.py', 'return text.lower().strip().replace(" ", "-")', 'return "-".join(text.lower().split())'),
        'mini-discount-004': ('checkout.py', 'price * (1 + discount_percent / 100)', 'price * (1 - discount_percent / 100)'),
    }
    with temporary_repo(repo) as work:
        assert not run_pytest(work)['passed']
        apply_exact_edit(work, *fixes[task['task_id']])
        assert run_pytest(work)['passed']
