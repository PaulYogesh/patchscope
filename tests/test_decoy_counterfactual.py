"""Counterfactual comparison guardrails: fixture byte parity and paired run identity."""
from __future__ import annotations

from pathlib import Path

import pytest

from patchscope.decoy_counterfactual import compare_variants, validate_fixture_pairs
from patchscope.experiment import build_schedule, load_manifest
from scripts.compare_decoy_presence import render

ROOT = Path(__file__).resolve().parents[1]


def manifests():
    clean = load_manifest(ROOT / 'experiments/decoy_free_native_v031.json')
    decoy = load_manifest(ROOT / 'experiments/interference_smoke_v030.json')
    return clean, decoy


def record(exp: str, task_id: str, seed: int, *, repair: bool, patch: str) -> dict:
    return {
        'experiment_id': exp, 'task_id': task_id, 'condition': 'native',
        'repetition': 0,
        'run_id': f'{task_id}__native__r00',
        'provenance': {
            'generation': {'model': 'qwen3.5:9b', 'temperature': 0,
                           'seed': seed, 'tool_policy': 'native_required'},
            'prompt_version': 'v023', 'tool_schema_sha256': 'toolhash',
            'ollama': {'digest': 'modeldigest'},
        },
        'budgets': {'max_steps': 6, 'max_patch_completion_tokens_per_call': 1400},
        'trajectory': [{'kind': 'patch_proposal', 'path': patch, 'old': 'a', 'new': 'b'}],
        'proposal': {'path': patch, 'old': 'a', 'new': 'b'},
        'outcome': {'status': 'resolved' if repair else 'repair_failed_tests',
                    'repair_verified': repair},
        'usage': {'total_tokens': 1234},
        'intervention': {'sources': []},
    }


def make_pairs():
    clean, decoy = manifests()
    schedule = build_schedule(clean)
    seeds = {item['task_id']: item['model_seed'] for item in schedule
             if item['condition'] == 'native'}
    a = [record(clean['experiment_id'], task_id, seeds[task_id], repair=True,
                patch=task['oracle']['paths'][0]) for task_id, task in
         [(t['task_id'], t) for t in clean['tasks']]]
    b = [record(decoy['experiment_id'], task_id, seeds[task_id], repair=True,
                patch=task['oracle']['paths'][0]) for task_id, task in
         [(t['task_id'], t) for t in decoy['tasks']]]
    return clean, decoy, a, b


def test_fixture_parity_is_exactly_one_decoy_per_task():
    clean, decoy = manifests()
    rows = validate_fixture_pairs(clean, decoy, ROOT)
    assert len(rows) == 4
    assert {r['decoy_path'] for r in rows} == {
        'average_utils.py', 'bounds_compat.py', 'slugify.py', 'pricing_compat.py'
    }
    assert all(len(r['shared_files_sha256']) == 64 for r in rows)


def test_schedule_matches_seeds_for_native_on_both_manifests():
    clean, decoy = manifests()
    def selected(manifest):
        return {(r['task_id'], r['repetition']): r['model_seed']
                for r in build_schedule(manifest) if r['condition'] == 'native'}
    assert selected(clean) == selected(decoy)
    assert len(selected(clean)) == 4


def test_compare_paired_success_flip_and_wrong_file_edit():
    clean, decoy, a, b = make_pairs()
    b[0]['outcome'] = {'status': 'repair_failed_tests', 'repair_verified': False}
    b[0]['proposal']['path'] = decoy['tasks'][0]['misleading_pool'][0]
    b[0]['trajectory'][0]['path'] = decoy['tasks'][0]['misleading_pool'][0]
    result = compare_variants(a, b, clean, decoy, ROOT)
    assert result['summary']['clean_verified'] == 4
    assert result['summary']['decoy_verified'] == 3
    assert result['summary']['lost_with_decoy'] == 1
    assert result['summary']['decoy_wrong_locus_patches'] == 1
    assert result['n_tasks'] == result['n_pairs'] == 4
    text = render(result)
    assert 'repository-composition' in text
    assert 'average_utils.py' in text


def test_rejects_different_model_seed():
    clean, decoy, a, b = make_pairs()
    b[0]['provenance']['generation']['seed'] += 1
    with pytest.raises(ValueError, match='Generation/model/protocol mismatch'):
        compare_variants(a, b, clean, decoy, ROOT)


def test_rejects_missing_runs():
    clean, decoy, a, b = make_pairs()
    with pytest.raises(ValueError, match='Incomplete native pairs'):
        compare_variants(a, b[:-1], clean, decoy, ROOT)


def test_rejects_unverified_episode():
    clean, decoy, a, b = make_pairs()
    a[0]['outcome']['status'] = 'proposal_requires_explicit_verification_opt_in'
    with pytest.raises(ValueError, match='Verification was not performed'):
        compare_variants(a, b, clean, decoy, ROOT)


def test_rejects_modified_shared_source_or_extra_file(tmp_path):
    clean, decoy = manifests()
    for task in clean['tasks']:
        name = Path(task['repo_path']).name
        src = ROOT / task['repo_path']
        dst = tmp_path / name
        import shutil
        shutil.copytree(src, dst)
        task['repo_path'] = name
    (tmp_path / 'mini_repo' / 'calculator.py').write_text('changed!', encoding='utf-8')
    with pytest.raises(ValueError, match='non-decoy fixture difference'):
        validate_fixture_pairs(clean, decoy, tmp_path)


def test_rejects_changed_generation_budget():
    clean, decoy = manifests()
    decoy['budgets']['max_patch_completion_tokens_per_call'] = 4000
    with pytest.raises(ValueError, match='Protocol differs'):
        validate_fixture_pairs(clean, decoy, ROOT)
