"""Native-agent three-way control: no extra module / neutral same-name / decoy.

The clean↔neutral comparison changes file presence and filename availability.
The neutral↔decoy comparison holds file paths/count fixed while replacing the
single added module's contents. These four curated examples support only a
small within-task engineering experiment, not a general population estimate.
"""
from __future__ import annotations

import ast
import hashlib
import statistics
from pathlib import Path

from patchscope.decoy_counterfactual import (
    _fixture_files, _generator_identity, _index, _task_map, validate_fixture_pairs,
)
from patchscope.trajectory_audit import audit_record, trajectory_signature


def validate_content_variants(clean: dict, neutral: dict, decoy: dict,
                              root: Path) -> list[dict]:
    """Demand exact shared bytes and equal filenames, with a single content swap.

    Neutral material is valid source but *not* the misleading implementation;
    the same-named decoy is present under both treatments. A small length
    discrepancy is tolerated and explicitly recorded (character counts do not
    imply equal model tokens).
    """
    validate_fixture_pairs(clean, decoy, root)
    validate_fixture_pairs(clean, neutral_with_decoy_labels(neutral, decoy), root)
    maps = [_task_map(m) for m in (clean, neutral, decoy)]
    if not (set(maps[0]) == set(maps[1]) == set(maps[2])):
        raise ValueError('Task sets differ across content variants')
    for field in ('repetitions', 'randomization_seed', 'model_seed_base', 'model',
                  'budgets', 'retrieval'):
        if not (clean[field] == neutral[field] == decoy[field]):
            raise ValueError(f'Protocol differs across content variants: {field}')
    rows = []
    for task_id in sorted(maps[0]):
        a, b, c = (mapping[task_id] for mapping in maps)
        for field in ('oracle', 'placebo_pool', 'trusted_execution', 'verification'):
            if not (a[field] == b[field] == c[field]):
                raise ValueError(f'{task_id}: {field} differs across variants')
        a_files = _fixture_files(root / a['repo_path'])
        b_files = _fixture_files(root / b['repo_path'])
        c_files = _fixture_files(root / c['repo_path'])
        decoy_paths = c.get('misleading_pool') or []
        if len(decoy_paths) != 1:
            raise ValueError(f'{task_id}: expected one labeled decoy path')
        extra = decoy_paths[0]
        if set(b_files) != set(c_files) or set(b_files) != (set(a_files) | {extra}):
            raise ValueError(f'{task_id}: filenames do not match the three-way contract')
        changed = {p for p in b_files if b_files[p] != c_files[p]}
        if changed != {extra}:
            raise ValueError(f'{task_id}: expected only changed decoy content: {changed}')
        neutral_bytes, decoy_bytes = b_files[extra], c_files[extra]
        if not neutral_bytes or not decoy_bytes:
            raise ValueError(f'{task_id}: empty extra module')
        length_gap = (len(neutral_bytes) - len(decoy_bytes)) / len(decoy_bytes)
        if abs(length_gap) > .10:
            raise ValueError(f'{task_id}: extra-module byte lengths differ >10%')
        # Verify the same path contains disjoint function names in both files.
        try:
            n_ast = ast.parse(neutral_bytes.decode('utf-8'))
            d_ast = ast.parse(decoy_bytes.decode('utf-8'))
        except (UnicodeError, SyntaxError) as exc:
            raise ValueError(f'{task_id}: invalid source in extra module') from exc
        def functions(tree):
            return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        neutral_funcs, decoy_funcs = functions(n_ast), functions(d_ast)
        if not neutral_funcs or not decoy_funcs or neutral_funcs & decoy_funcs:
            raise ValueError(f'{task_id}: neutral module shares decoy function names')
        rows.append({
            'task_id': task_id, 'extra_path': extra,
            'neutral_bytes': len(neutral_bytes), 'decoy_bytes': len(decoy_bytes),
            'neutral_minus_decoy_bytes': len(neutral_bytes) - len(decoy_bytes),
            'neutral_sha256': hashlib.sha256(neutral_bytes).hexdigest(),
            'decoy_sha256': hashlib.sha256(decoy_bytes).hexdigest(),
        })
    return rows


def neutral_with_decoy_labels(neutral: dict, decoy: dict) -> dict:
    """Supply decoy path labels only to fixture validation, never to an agent."""
    import copy
    proxy = copy.deepcopy(neutral)
    dmap = _task_map(decoy)
    for t in proxy['tasks']:
        t['misleading_pool'] = list(dmap[t['task_id']]['misleading_pool'])
    return proxy


def compare_content_variants(clean_records: list[dict], neutral_records: list[dict],
                             decoy_records: list[dict], clean_manifest: dict,
                             neutral_manifest: dict, decoy_manifest: dict,
                             root: Path) -> dict:
    parity = validate_content_variants(clean_manifest, neutral_manifest, decoy_manifest, root)
    indices = [
        _index(records, manifest, 'native')
        for records, manifest in (
            (clean_records, clean_manifest), (neutral_records, neutral_manifest),
            (decoy_records, decoy_manifest),
        )
    ]
    expected = {(t['task_id'], rep) for t in clean_manifest['tasks']
                for rep in range(clean_manifest['repetitions'])}
    for label, index in zip(('clean', 'neutral', 'decoy'), indices):
        if set(index) != expected:
            raise ValueError(f'Incomplete {label} native runs: missing={sorted(expected-set(index))}')
    decoys = {t['task_id']: t['misleading_pool'] for t in decoy_manifest['tasks']}
    oracles = {t['task_id']: t['oracle']['paths'] for t in clean_manifest['tasks']}
    rows = []
    for task_id, rep in sorted(expected):
        trio = [index[(task_id, rep)] for index in indices]
        identities = [_generator_identity(x) for x in trio]
        if any(None in ident for ident in identities) or len(set(identities)) != 1:
            raise ValueError(f'Model/seed/protocol provenance differs: {task_id}, r{rep:02d}')
        if not (trio[0].get('budgets') == trio[1].get('budgets') == trio[2].get('budgets')):
            raise ValueError(f'Recorded budgets differ: {task_id}')
        for rec in trio:
            outcome = rec.get('outcome') or {}
            if outcome.get('status') == 'proposal_requires_explicit_verification_opt_in':
                raise ValueError(f'Unverified execution: {task_id}')
        audits = [audit_record(record, oracles[task_id], decoys[task_id]) for record in trio]
        result = {'task_id': task_id, 'repetition': rep}
        for label, rec, audit in zip(('clean', 'neutral', 'decoy'), trio, audits):
            result[label] = {
                'status': rec['outcome']['status'],
                'verified': bool(rec['outcome'].get('repair_verified')),
                'first_read_path': audit['first_read_path'],
                'patch_path': (rec.get('proposal') or {}).get('path'),
                'extra_path_patch': audit['patch_in_misleading_file'] is True,
                'total_tokens': rec['usage']['total_tokens'],
                'trajectory_signature': trajectory_signature(rec),
            }
        result['neutral_minus_clean_tokens'] = result['neutral']['total_tokens'] - result['clean']['total_tokens']
        result['decoy_minus_neutral_tokens'] = result['decoy']['total_tokens'] - result['neutral']['total_tokens']
        result['neutral_to_decoy_loss'] = result['neutral']['verified'] and not result['decoy']['verified']
        rows.append(result)
    return {
        'comparison': 'native_clean_vs_same_name_neutral_vs_task_relevant_decoy',
        'experiments': {label: m['experiment_id'] for label, m in
                        (('clean', clean_manifest), ('neutral', neutral_manifest), ('decoy', decoy_manifest))},
        'n_distinct_tasks': len(parity), 'n_matched_episodes': len(rows),
        'fixture_parity': parity,
        'summary': {
            **{f'{label}_verified': sum(r[label]['verified'] for r in rows)
               for label in ('clean', 'neutral', 'decoy')},
            'lost_neutral_to_decoy': sum(r['neutral_to_decoy_loss'] for r in rows),
            'gained_neutral_to_decoy': sum(not r['neutral']['verified'] and r['decoy']['verified'] for r in rows),
            'neutral_extra_path_edits': sum(r['neutral']['extra_path_patch'] for r in rows),
            'decoy_extra_path_edits': sum(r['decoy']['extra_path_patch'] for r in rows),
            'median_neutral_minus_clean_tokens': statistics.median(r['neutral_minus_clean_tokens'] for r in rows),
            'median_decoy_minus_neutral_tokens': statistics.median(r['decoy_minus_neutral_tokens'] for r in rows),
        },
        'pairs': rows,
    }
