"""Offline paired comparison for v0.5 patch-stage evidence policies.

The exploration trace must be identical within each matched task, or the
result is explicitly flagged as NOT a frozen-exploration comparison.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_native_records(root: Path, experiment: str) -> dict:
    directory = root / "runs" / experiment
    found = {}
    for p in sorted(directory.glob("*__native__r*.json")):
        record = json.loads(p.read_text(encoding="utf-8"))
        if record.get("condition") != "native":
            continue
        key = (record["task_id"], record["repetition"])
        if key in found:
            raise ValueError("duplicate_native_run")
        found[key] = record
    return found


def _preproposal_view(record: dict) -> tuple:
    """Comparable logged tool actions and evidence, excluding proposal stage."""
    rows = []
    for e in record.get("trajectory", []):
        if e.get("kind") in {"tool_call", "tool_result"}:
            item = {k: v for k, v in e.items() if k not in {"event_index"}}
            rows.append(item)
    return tuple(json.dumps(r, sort_keys=True) for r in rows)


def compare_policies(arms: dict[str, dict]) -> dict:
    if set(arms) != {"baseline", "inventory", "imports"}:
        raise ValueError("expected_baseline_inventory_imports")
    keys = [set(record_set) for record_set in arms.values()]
    if not all(keys) or any(k != keys[0] for k in keys):
        raise ValueError("incomplete_or_unmatched_native_runs")
    rows=[]
    for key in sorted(keys[0]):
        group={name: arm[key] for name,arm in arms.items()}
        if any(r.get('outcome',{}).get('status') == 'incomplete' for r in group.values()):
            raise ValueError('incomplete_episode')
        seeds={r.get("provenance",{}).get("generation",{}).get("seed") for r in group.values()}
        digests={r.get("provenance",{}).get("ollama",{}).get("digest") for r in group.values()}
        models={r.get("provenance",{}).get("generation",{}).get("model") for r in group.values()}
        budgets={json.dumps({k: v for k, v in r.get("budgets",{}).items()
                             if k != 'source_map_char_budget'},sort_keys=True) for r in group.values()}
        if len(seeds)!=1 or None in seeds or len(digests)!=1 or len(models)!=1 or len(budgets)!=1:
            raise ValueError(f"model_seed_or_budget_mismatch:{key[0]}")
        policy_check = {
            name: r.get('proposal_evidence',{}).get('policy','off') for name,r in group.items()
        }
        if policy_check != {'baseline':'off','inventory':'inventory','imports':'imports'}:
            raise ValueError(f"evidence_policy_mismatch:{key[0]}")
        tool_paths = {_preproposal_view(r) for r in group.values()}
        observed_sets = {tuple(sorted(r.get('observed_paths',[]))) for r in group.values()}
        matching_exploration = len(tool_paths)==1 and len(observed_sets)==1
        rows.append({
            'task_id':key[0], 'repetition':key[1],
            'exploration_log_match':matching_exploration,
            'outcomes': {n:r['outcome']['status'] for n,r in group.items()},
            'verified':{n:bool(r['outcome']['repair_verified']) for n,r in group.items()},
            'patch_paths':{n:(r.get('proposal') or {}).get('path') for n,r in group.items()},
            'tokens':{n:r['usage']['total_tokens'] for n,r in group.items()},
            'map_chars':{n:r.get('proposal_evidence',{}).get('chars',0) for n,r in group.items()},
            'map_edges':group['imports'].get('proposal_evidence',{}).get('static_edges'),
        })
    return {
        'n_tasks':len({r['task_id'] for r in rows}), 'n_pairs':len(rows),
        'n_matching_exploration':sum(r['exploration_log_match'] for r in rows),
        'results': rows,
        'warning': ('A matched exploration log is not proof of identical hidden state; '
                    'inventory and imports prompts are not token-length matched. '
                    'Only task-level descriptive comparisons are warranted.'),
    }


def render_comparison(report: dict) -> str:
    rows=[
        '# PatchScope v0.5 — patch-stage dependency evidence', '',
        f"Compared **{report['n_pairs']}** matched episodes over **{report['n_tasks']}** tasks.",
        f"Identical recorded exploration: **{report['n_matching_exploration']}/{report['n_pairs']}**.", '',
        '| Task | Same exploration | Baseline | Inventory | Static imports | Patch path (off → inventory → imports) |',
        '|---|---|---|---|---|---|',
    ]
    def label(x):return 'verified' if x else 'failed'
    for item in report['results']:
        patches=' → '.join('`'+str(item['patch_paths'][k])+'`' for k in ('baseline','inventory','imports'))
        rows.append('| '+' | '.join([
            '`'+item['task_id']+'`',
            'yes' if item['exploration_log_match'] else 'NO',
            *[label(item['verified'][k]) for k in ('baseline','inventory','imports')],
            patches,
        ])+' |')
    rows += ['', '## Interpretation', '', report['warning'], '',
             'Static import edges are unverified source relationships, not executable reachability evidence. '
             'This is a development-set diagnostic: do not claim generality or new benchmark significance.', '']
    return '\n'.join(rows)
