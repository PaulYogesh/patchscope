"""Strict matched two-arm pilot comparisons for public reproduction evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from patchscope.experiment import PROJECT_ROOT


def _native_records(root: Path, experiment: str) -> dict:
    folder = root / 'runs' / experiment
    results = {}
    if not folder.is_dir():
        raise ValueError(f'missing_experiment:{experiment}')
    for file in sorted(folder.glob('*.json')):
        rec = json.loads(file.read_text())
        if rec.get('experiment_id') != experiment or rec.get('condition') != 'native':
            continue
        k = (rec['task_id'], rec['repetition'])
        if k in results:
            raise ValueError('duplicate_native_record')
        results[k] = rec
    return results


def _exploration_fingerprint(record: dict) -> str:
    rows = [e for e in record.get('trajectory', []) if
            e.get('kind') in {'tool_call','tool_result'} or
            (e.get('kind') == 'model_response' and e.get('purpose') == 'exploration')]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def compare_operative(root: Path = PROJECT_ROOT,
                      off_id: str = 'operative-off-v060',
                      trace_id: str = 'operative-trace-v060') -> dict:
    off, traced = _native_records(root, off_id), _native_records(root, trace_id)
    if not off or off.keys() != traced.keys():
        raise ValueError('incomplete_or_unmatched_operative_episodes')
    rows = []
    for key in sorted(off):
        a, b = off[key], traced[key]
        if (a.get('operative_trace_policy', 'off') != 'off'
                or b.get('operative_trace_policy') != 'public_reproducer'
                or not b.get('operative_trace')):
            raise ValueError(f'operative_policy_or_trace_missing:{key}')
        for record in [a, b]:
            if record.get('outcome', {}).get('status') in (None, 'incomplete'):
                raise ValueError(f'incomplete_operative_run:{key}')
        def provenance(rec):
            p = rec.get('provenance', {})
            return (p.get('generation', {}).get('model'), p.get('generation', {}).get('seed'),
                    p.get('generation', {}).get('temperature'),
                    p.get('ollama', {}).get('digest'), p.get('source_tree_sha256'))
        pa, pb = provenance(a), provenance(b)
        if pa != pb or pa[3] in (None, 'unavailable'):
            raise ValueError(f'operative_provenance_mismatch:{key}')
        if not b['operative_trace']['reproducer_failed']:
            raise ValueError(f'operative_reproducer_did_not_fail:{key}')
        rows.append({
            'task_id': key[0], 'repetition': key[1],
            'off_verified': bool(a['outcome']['repair_verified']),
            'trace_verified': bool(b['outcome']['repair_verified']),
            'off_status': a['outcome']['status'], 'trace_status': b['outcome']['status'],
            'off_patch': (a.get('proposal') or {}).get('path'),
            'trace_patch': (b.get('proposal') or {}).get('path'),
            'trace_executed_paths': b['operative_trace']['executed_paths'],
            'trace_patch_executed': (b.get('proposal') or {}).get('path') in b['operative_trace']['executed_paths'],
            'identical_exploration': _exploration_fingerprint(a) == _exploration_fingerprint(b),
            'delta_tokens': b['usage']['total_tokens'] - a['usage']['total_tokens'],
        })
    return {'n_tasks': len({r['task_id'] for r in rows}),
            'n_matched':len(rows),'rows':rows,
            'off_verified':sum(r['off_verified'] for r in rows),
            'trace_verified':sum(r['trace_verified'] for r in rows)}


def render_operative(report: dict) -> str:
    lines = ['# PatchScope v0.6 — public execution-evidence pilot','',
             f"Matched {report['n_matched']} native episodes across {report['n_tasks']} fresh dynamic-dispatch tasks.",
             '', '| Task | Off outcome | Public trace outcome | Off patch | Trace patch | Trace patch executed? | Same exploration? | Δ tokens |',
             '|---|---|---|---|---|---|---|---:|']
    for row in report['rows']:
        lines.append('| ' + ' | '.join([
            f"`{row['task_id']}`", row['off_status'], row['trace_status'],
            f"`{row['off_patch']}`", f"`{row['trace_patch']}`",
            'yes' if row['trace_patch_executed'] else 'no',
            'yes' if row['identical_exploration'] else 'NO', str(row['delta_tokens']),
        ]) + ' |')
    lines += ['', f"Verified repairs: off **{report['off_verified']}/{report['n_matched']}**, "
                   f"public trace **{report['trace_verified']}/{report['n_matched']}**.", '',
              '## Limits', '',
              'A public reproducer is an extra source of external execution evidence, not hidden oracle labels. '
              'It may make a small synthetic task easier by exposing its operative path. '
              'This preliminary study uses two authored synthetic tasks and is neither a held-out benchmark '
              'nor proof of improvement. The public reproducer is separate from pytest verification tests; '
              'the public script and verifier still share the same contract and need more independent tasks.',
              '', 'Trace execution is only file-level observed execution, not proof of fault, code causality, '
              'or complete program reachability. Model seeds do not enforce deterministic exploration. '
              'Prompt size differs across arms. Model-generated code executes only with explicit local opt-in; '
              'disposable directories are not security sandboxes.', '']
    return '\n'.join(lines)
