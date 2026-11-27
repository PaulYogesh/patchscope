"""Post-hoc evidence-exposure and import-reference audit for native-agent controls.

No model calls, source execution, edits or unobserved model-state inferences.
The imported references are *static hints*, not a sound Python call graph.
"""
from __future__ import annotations

import ast
from pathlib import Path

from patchscope.content_counterfactual import compare_content_variants
from patchscope.retrieval import discover_files


def visible_importers(repo: Path, target_path: str) -> list[str]:
    """List accessible, non-test source modules statically importing target's module.

    Handles simple absolute imports. No claim about relative, dynamic, aliased
    packages or runtime reachability.
    """
    target = Path(target_path)
    module = '.'.join(target.with_suffix('').parts)
    result = []
    for path in discover_files(repo):
        rel = path.relative_to(repo).as_posix()
        if rel == target_path:
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except (UnicodeError, SyntaxError):
            continue
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                found |= node.module == module
            elif isinstance(node, ast.Import):
                found |= any(a.name == module or a.name.startswith(module + '.')
                             for a in node.names)
        if found:
            result.append(rel)
    return sorted(result)


def audit_content_exposure(clean_records: list[dict], neutral_records: list[dict],
                           decoy_records: list[dict], clean: dict, neutral: dict,
                           decoy: dict, root: Path) -> dict:
    """Report actual file exposure and distinguish content-contrast from seed effects."""
    comparison = compare_content_variants(clean_records, neutral_records,
                                          decoy_records, clean, neutral, decoy, root)
    clean_tasks = {x['task_id']: x for x in clean['tasks']}
    decoy_tasks = {x['task_id']: x for x in decoy['tasks']}
    provenance_pairs = {
        (r['task_id'], r['repetition']): r for r in comparison['pairs']
    }
    index = [{(r['task_id'], r['repetition']): r for r in records if r.get('condition') == 'native'}
             for records in (clean_records, neutral_records, decoy_records)]
    rows = []
    for key in sorted(provenance_pairs):
        task_id, repetition = key
        oracle_paths = clean_tasks[task_id]['oracle']['paths']
        decoy_path = decoy_tasks[task_id]['misleading_pool'][0]
        repo = root / decoy_tasks[task_id]['repo_path']
        imported_oracle = sorted(set().union(*(visible_importers(repo, path) for path in oracle_paths)))
        imported_decoy = visible_importers(repo, decoy_path)
        record_trio = [item[key] for item in index]
        exposures = []
        for label, record in zip(('clean', 'neutral', 'decoy'), record_trio):
            observed = set(record.get('observed_paths') or [])
            tool_reads = [e.get('arguments', {}).get('path') for e in record.get('trajectory', [])
                          if e.get('kind') == 'tool_call'
                          and e.get('name') == 'read_file' and e.get('valid') is True]
            seeded = {entry['path'] for entry in record.get('intervention', {}).get('sources', [])}
            exposures.append({
                'variant': label,
                'first_read': tool_reads[0] if tool_reads else None,
                'extra_file_read': decoy_path in tool_reads,
                'extra_file_observed': decoy_path in observed,
                'oracle_observed': bool(observed.intersection(oracle_paths)),
                'oracle_tool_read': bool(set(tool_reads).intersection(oracle_paths)),
                'seeded_extra_file': decoy_path in seeded,
                'n_unique_observed_files': len(observed),
                'n_valid_reads': len(tool_reads),
            })
        paired = provenance_pairs[key]
        rows.append({
            'task_id': task_id, 'repetition': repetition,
            'oracle_paths': oracle_paths, 'extra_path': decoy_path,
            'static_oracle_importers': imported_oracle,
            'static_extra_importers': imported_decoy,
            'clean_verified': paired['clean']['verified'],
            'neutral_verified': paired['neutral']['verified'],
            'decoy_verified': paired['decoy']['verified'],
            'decoy_extra_file_patch': paired['decoy']['extra_path_patch'],
            'exposures': {r['variant']: r for r in exposures},
        })
    return {
        'experiment_ids': comparison['experiments'],
        'n_distinct_tasks': comparison['n_distinct_tasks'],
        'rows': rows,
        'summary': {
            'decoy_observed': sum(r['exposures']['decoy']['extra_file_observed'] for r in rows),
            'decoy_first_read': sum(r['exposures']['decoy']['first_read'] == r['extra_path'] for r in rows),
            'decoy_wrong_locus_patches': sum(r['decoy_extra_file_patch'] for r in rows),
            'decoy_failures': sum(not r['decoy_verified'] for r in rows),
            'visible_oracle_importer_tasks': sum(bool(r['static_oracle_importers']) for r in rows),
            'visible_decoy_importer_tasks': sum(bool(r['static_extra_importers']) for r in rows),
        },
    }


def render_exposure_markdown(audits: dict[str, dict]) -> str:
    lines = ['# PatchScope — evidence-exposure diagnostic', '',
             'Offline descriptive analysis of recorded native-agent episodes. '
             'Paths and static imports are observable proxies, not model attention, '
             'causal mediation or proven runtime dependency.', '']
    for title, audit in audits.items():
        s = audit['summary']
        lines.extend([
            f'## {title}: {audit["n_distinct_tasks"]} tasks', '',
            f'Extra file observed by agent: **{s["decoy_observed"]}/{audit["n_distinct_tasks"]}**; '
            f'first read: **{s["decoy_first_read"]}**; wrong-file patches: '
            f'**{s["decoy_wrong_locus_patches"]}**; decoy-condition failures: '
            f'**{s["decoy_failures"]}**.', '',
            '| Task | Neutral first read | Decoy first read | Decoy observed | True-file observed | Visible importer of true module | Decoy patched | Decoy verified |',
            '|---|---|---|---|---|---|---|---|',
        ])
        for row in audit['rows']:
            neutral = row['exposures']['neutral']
            decoy = row['exposures']['decoy']
            def yn(x): return 'yes' if x else 'no'
            def code(x): return f'`{x}`' if x else '—'
            lines.append('| ' + ' | '.join((
                code(row['task_id']), code(neutral['first_read']),
                code(decoy['first_read']), yn(decoy['extra_file_observed']),
                yn(decoy['oracle_observed']),
                ', '.join(map(code, row['static_oracle_importers'])) or '—',
                yn(row['decoy_extra_file_patch']), yn(row['decoy_verified']),
            )) + ' |')
        lines.extend(['',
            'Static import checks consider accessible non-test Python modules only. '
            'They do not prove that an import was executed or that a file caused the reported behavior.',
            ''])
    lines.extend(['## Interpretation gate', '',
        'If a decoy was never observed, its source content cannot directly account for a later '
        'model decision through a displayed read or seed. Filename presence and file lists '
        'remain possible influences. If the decoy was observed and a wrong-locus patch followed, '
        'this is compatible with distraction, but it does not establish hidden reasoning.', '',
        'Do not pool earlier hand-selected tasks with newer tasks without accounting for '
        'their different construction protocols.'])
    return '\n'.join(lines) + '\n'
