"""Pair existing v0.3 native runs with clean-repository v0.3.1 counterfactuals.

No model inference or code execution. Requires matching frozen generator settings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from patchscope.decoy_counterfactual import compare_variants
from patchscope.experiment import PROJECT_ROOT, load_manifest


def _records(experiment_id: str) -> list[dict]:
    directory = PROJECT_ROOT / 'runs' / experiment_id
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(directory.glob('*.json'))]


def render(summary: dict) -> str:
    s = summary['summary']
    lines = [
        '# PatchScope — decoy presence counterfactual (native exploration)', '',
        f"Compared {summary['n_pairs']} matched episodes across {summary['n_tasks']} distinct tasks.",
        'The clean fixture has exactly the same shared files and issue/test bytes as the decoy fixture, '
        'but the decoy fixture adds one curated wrong-locus source file. '
        'The model, random seed, prompt/tool protocol and budgets are checked for equality.', '',
        '| Task | Clean outcome | Decoy-present outcome | Clean patch | Decoy-present patch | Wrong-locus edit | Δ tokens |',
        '|---|---|---|---|---|---|---:|',
    ]
    for row in summary['pairs']:
        lines.append(f"| `{row['task_id']}` | {row['clean_status']} | {row['decoy_status']} | "
                     f"`{row['clean_patch_path'] or '—'}` | `{row['decoy_patch_path'] or '—'}` | "
                     f"{'yes' if row['decoy_wrong_locus_patch'] else 'no'} | {row['decoy_minus_clean_tokens']:+} |")
    lines.extend(['', '## Descriptive summary', '',
                  f"- Clean verified: **{s['clean_verified']}/{summary['n_pairs']}**",
                  f"- Decoy-present verified: **{s['decoy_verified']}/{summary['n_pairs']}**",
                  f"- Lost verified repair with decoy present: **{s['lost_with_decoy']}**",
                  f"- Gained verified repair with decoy present: **{s['gained_with_decoy']}**",
                  f"- Wrong-locus patches with decoy present: **{s['decoy_wrong_locus_patches']}**",
                  f"- Identical recorded action/patch sequences: **{s['identical_recorded_trajectories']}**",
                  f"- Median decoy-minus-clean tokens: **{s['median_extra_tokens']:+}**", '',
                  '## Interpretation and limitations', '',
                  'This is a controlled **repository-composition** comparison, not the incremental '
                  'effect of injecting a misleading seed. Decoy code is absent in one environment '
                  'and present, readable, and retrievable in the other. Adding a file can change '
                  'file lists, BM25 scores and exploration choices. All of these are part of this '
                  'treatment, not separately identified mechanisms.', '',
                  'The four synthetic tasks are not sufficient for a population claim. '
                  'Model seeds and generator configuration are matched, but local model '
                  'execution may not be perfectly deterministic. No independence or '
                  'significance claim is made for within-task repetitions. '
                  'Verified success requires baseline failure and patched-test success; '
                  'review underlying JSON and edited diffs for individual cases.', ''])
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean-manifest', type=Path,
                        default=PROJECT_ROOT / 'experiments/decoy_free_native_v031.json')
    parser.add_argument('--decoy-manifest', type=Path,
                        default=PROJECT_ROOT / 'experiments/interference_smoke_v030.json')
    args = parser.parse_args(argv)
    clean, decoy = load_manifest(args.clean_manifest), load_manifest(args.decoy_manifest)
    summary = compare_variants(_records(clean['experiment_id']), _records(decoy['experiment_id']),
                               clean, decoy, PROJECT_ROOT)
    report_base = PROJECT_ROOT / 'reports/decoy-presence-v031'
    report_base.parent.mkdir(exist_ok=True, parents=True)
    report_base.with_suffix('.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    report_base.with_suffix('.md').write_text(render(summary), encoding='utf-8')
    print(f"Wrote {report_base.with_suffix('.md')} and .json ({summary['n_pairs']} matched native runs)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
