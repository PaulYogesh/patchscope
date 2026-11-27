"""Compare decoy-absent and decoy-present runs without repeating prior model calls.

This is a *repository-composition* intervention, NOT an estimator of the
additional effect of explicitly seeding a misleading excerpt. The design
requires byte-identical shared fixture files, identical tasks and generator
settings, and equal paired model seeds.
"""
from __future__ import annotations

import hashlib
import statistics
from pathlib import Path

from patchscope.trajectory_audit import audit_record, trajectory_signature


def _task_map(manifest: dict) -> dict[str, dict]:
    tasks = {t['task_id']: t for t in manifest['tasks']}
    if len(tasks) != len(manifest['tasks']):
        raise ValueError('Duplicate task ID')
    return tasks


def _fixture_files(path: Path) -> dict[str, bytes]:
    return {
        p.relative_to(path).as_posix(): p.read_bytes()
        for p in path.rglob('*') if p.is_file()
        and not any(part.startswith('.') or part == '__pycache__'
                    for part in p.relative_to(path).parts)
    }


def validate_fixture_pairs(clean: dict, decoy: dict, root: Path) -> list[dict]:
    """Refuse to compare anything but exactly one new curated decoy per task."""
    clean_tasks, decoy_tasks = _task_map(clean), _task_map(decoy)
    if set(clean_tasks) != set(decoy_tasks):
        raise ValueError('Task sets differ between repository variants')
    for field in ('repetitions', 'randomization_seed', 'model_seed_base',
                  'model', 'budgets', 'retrieval'):
        if clean[field] != decoy[field]:
            raise ValueError(f'Protocol differs across variants: {field}')
    out = []
    for task_id in sorted(clean_tasks):
        a, b = clean_tasks[task_id], decoy_tasks[task_id]
        for field in ('oracle', 'placebo_pool', 'trusted_execution', 'verification'):
            if a[field] != b[field]:
                raise ValueError(f'{task_id}: evaluator/test config differs: {field}')
        wrong_locus = b.get('misleading_pool') or []
        if len(wrong_locus) != 1:
            raise ValueError(f'{task_id}: expected exactly one curated decoy')
        clean_repo = (root / a['repo_path']).resolve()
        decoy_repo = (root / b['repo_path']).resolve()
        left, right = _fixture_files(clean_repo), _fixture_files(decoy_repo)
        added = set(right) - set(left)
        removed = set(left) - set(right)
        changed = {p for p in (set(left) & set(right)) if left[p] != right[p]}
        if added != set(wrong_locus) or removed or changed:
            raise ValueError(f'{task_id}: non-decoy fixture difference: '
                             f'added={sorted(added)} removed={sorted(removed)} changed={sorted(changed)}')
        if left.get('issue.md') is None:
            raise ValueError(f'{task_id}: missing shared issue.md')
        checksum = hashlib.sha256()
        for name in sorted(left):
            checksum.update(name.encode() + b'\0' + hashlib.sha256(left[name]).digest())
        out.append({'task_id': task_id, 'decoy_path': wrong_locus[0],
                    'shared_files_sha256': checksum.hexdigest(),
                    'shared_file_count': len(left)})
    return out


def _index(records: list[dict], manifest: dict, condition: str) -> dict[tuple, dict]:
    indexed = {}
    for record in records:
        if record.get('experiment_id') != manifest['experiment_id']:
            raise ValueError('Run record experiment ID mismatch')
        if record.get('condition') != condition:
            continue
        key = (record['task_id'], record['repetition'])
        if key in indexed:
            raise ValueError(f'Duplicate record: {key}')
        indexed[key] = record
    return indexed


def _generator_identity(record: dict) -> tuple:
    prov = record.get('provenance', {})
    gen = prov.get('generation', {})
    return (gen.get('model'), gen.get('seed'), gen.get('temperature'),
            gen.get('tool_policy'), prov.get('prompt_version'),
            prov.get('tool_schema_sha256'),
            prov.get('ollama', {}).get('digest'))


def compare_variants(clean_records: list[dict], decoy_records: list[dict],
                     clean_manifest: dict, decoy_manifest: dict,
                     root: Path, *, condition: str = 'native') -> dict:
    if condition != 'native':
        raise ValueError('v0.3.1 controls only native exploration; other arms need a separate protocol')
    fixture_pairs = validate_fixture_pairs(clean_manifest, decoy_manifest, root)
    left = _index(clean_records, clean_manifest, condition)
    right = _index(decoy_records, decoy_manifest, condition)
    expected = {(t['task_id'], rep) for t in clean_manifest['tasks']
                for rep in range(clean_manifest['repetitions'])}
    if set(left) != expected or set(right) != expected:
        raise ValueError(f'Incomplete native pairs: clean missing={sorted(expected-set(left))}, '
                         f'decoy missing={sorted(expected-set(right))}')
    decoys = {t['task_id']: t['misleading_pool'] for t in decoy_manifest['tasks']}
    oracles = {t['task_id']: t['oracle']['paths'] for t in decoy_manifest['tasks']}
    rows = []
    for task_id, repetition in sorted(expected):
        a, b = left[(task_id, repetition)], right[(task_id, repetition)]
        pa, pb = _generator_identity(a), _generator_identity(b)
        if None in pa or None in pb or pa != pb:
            raise ValueError(f'Generation/model/protocol mismatch or missing provenance: {task_id}, rep={repetition}: {pa} != {pb}')
        if a.get('budgets') != b.get('budgets'):
            raise ValueError(f'Budgets differ: {task_id}')
        for r in (a, b):
            if r.get('outcome', {}).get('status') == 'proposal_requires_explicit_verification_opt_in':
                raise ValueError(f'Verification was not performed: {task_id}')
        audit_a = audit_record(a, oracles[task_id])
        audit_b = audit_record(b, oracles[task_id], decoys[task_id])
        rows.append({
            'task_id': task_id, 'repetition': repetition,
            'clean_status': a['outcome']['status'],
            'decoy_status': b['outcome']['status'],
            'clean_verified': bool(a['outcome'].get('repair_verified')),
            'decoy_verified': bool(b['outcome'].get('repair_verified')),
            'clean_first_read': audit_a['first_read_path'],
            'decoy_first_read': audit_b['first_read_path'],
            'clean_patch_path': (a.get('proposal') or {}).get('path'),
            'decoy_patch_path': (b.get('proposal') or {}).get('path'),
            'decoy_wrong_locus_patch': audit_b['patch_in_misleading_file'] is True,
            'identical_recorded_trajectory': trajectory_signature(a) == trajectory_signature(b),
            'clean_tokens': a['usage']['total_tokens'],
            'decoy_tokens': b['usage']['total_tokens'],
            'decoy_minus_clean_tokens': b['usage']['total_tokens'] - a['usage']['total_tokens'],
        })
    # task count is explicit, not total repetitions, for research interpretation.
    return {
        'comparison': 'decoy_presence_vs_absence__native',
        'clean_experiment': clean_manifest['experiment_id'],
        'decoy_experiment': decoy_manifest['experiment_id'],
        'n_tasks': len(fixture_pairs), 'n_pairs': len(rows),
        'fixture_parity': fixture_pairs,
        'summary': {
            'clean_verified': sum(r['clean_verified'] for r in rows),
            'decoy_verified': sum(r['decoy_verified'] for r in rows),
            'lost_with_decoy': sum(r['clean_verified'] and not r['decoy_verified'] for r in rows),
            'gained_with_decoy': sum(not r['clean_verified'] and r['decoy_verified'] for r in rows),
            'decoy_wrong_locus_patches': sum(r['decoy_wrong_locus_patch'] for r in rows),
            'identical_recorded_trajectories': sum(r['identical_recorded_trajectory'] for r in rows),
            'median_extra_tokens': statistics.median(r['decoy_minus_clean_tokens'] for r in rows),
        },
        'pairs': rows,
    }
