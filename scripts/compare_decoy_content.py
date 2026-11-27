"""Compare three matched repository variants using saved run records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from patchscope.content_counterfactual import compare_content_variants
from patchscope.experiment import PROJECT_ROOT, load_manifest


def records(experiment_id: str, root: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding='utf-8'))
            for p in sorted((root / 'runs' / experiment_id).glob('*.json'))]


def render(result: dict) -> str:
    s = result['summary']
    lines = [
        '# PatchScope — same-filename decoy-content control', '',
        f"{result['n_matched_episodes']} paired native episodes; {result['n_distinct_tasks']} distinct tasks.", '',
        'All three repositories have byte-identical original source, issue and test files. '
        'The neutral and task-relevant decoy variants each add a Python file with the same '
        '**path**. Only that file\'s content differs, by at most 10% in byte length.', '',
        '| Task | Clean | Same-name neutral | Task-relevant decoy | Clean patch | Neutral patch | Decoy patch | Δ decoy−neutral tokens |',
        '|---|---|---|---|---|---|---|---:|',
    ]
    for r in result['pairs']:
        def status(label):
            item = r[label]
            return 'verified' if item['verified'] else item['status']
        lines.append(
            f"| `{r['task_id']}` | {status('clean')} | {status('neutral')} | {status('decoy')} | "
            f"`{r['clean']['patch_path'] or '—'}` | `{r['neutral']['patch_path'] or '—'}` | "
            f"`{r['decoy']['patch_path'] or '—'}` | {r['decoy_minus_neutral_tokens']:+} |"
        )
    lines.extend([
        '', '## Descriptive summary', '',
        f"- Clean verified: **{s['clean_verified']}/{result['n_matched_episodes']}**",
        f"- Same-name neutral verified: **{s['neutral_verified']}/{result['n_matched_episodes']}**",
        f"- Task-relevant decoy verified: **{s['decoy_verified']}/{result['n_matched_episodes']}**",
        f"- Success lost replacing neutral content with decoy content: **{s['lost_neutral_to_decoy']}**",
        f"- Success gained replacing neutral content with decoy content: **{s['gained_neutral_to_decoy']}**",
        f"- Patches to extra file: neutral **{s['neutral_extra_path_edits']}**, decoy **{s['decoy_extra_path_edits']}**",
        f"- Median extra tokens, neutral vs clean: **{s['median_neutral_minus_clean_tokens']:+}**",
        f"- Median extra tokens, decoy vs neutral: **{s['median_decoy_minus_neutral_tokens']:+}**", '',
        '## Scope and limitations', '',
        '**Clean → neutral** changes repository composition (adds a source file and filename). '
        '**Neutral → decoy** keeps the added filename, file count, and all other bytes fixed, '
        'but changes source contents. This identifies a *controlled content-substitution contrast*, '
        'not a universal mechanism or the independent effect of a misleading injected seed.', '',
        f'This is a {result["n_distinct_tasks"]}-task synthetic engineering control. Length matching is in source bytes, '
        'not model tokens. Model seeds and configurations are matched, but temperature zero '
        'does not guarantee fully deterministic inference. Do not infer population effects, '
        'hidden reasoning, or statistical significance. Review failed-test traces before claiming '
        'the agent relied on any specific excerpt.', '',
        '## Exact neutral/decoy file parity', '',
        '| Task | Shared extra filename | Neutral bytes | Decoy bytes |',
        '|---|---|---:|---:|',
    ])
    for p in result['fixture_parity']:
        lines.append(f"| `{p['task_id']}` | `{p['extra_path']}` | {p['neutral_bytes']} | {p['decoy_bytes']} |")
    lines.append('')
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean-manifest', type=Path,
                        default=PROJECT_ROOT / 'experiments/decoy_free_native_v031.json')
    parser.add_argument('--neutral-manifest', type=Path,
                        default=PROJECT_ROOT / 'experiments/same_name_neutral_v032.json')
    parser.add_argument('--decoy-manifest', type=Path,
                        default=PROJECT_ROOT / 'experiments/interference_smoke_v030.json')
    parser.add_argument('--output-prefix', type=Path, default=Path('reports/decoy-content-v032'))
    args = parser.parse_args(argv)
    manifests = [load_manifest(path) for path in
                 (args.clean_manifest, args.neutral_manifest, args.decoy_manifest)]
    result = compare_content_variants(
        *(records(m['experiment_id'], PROJECT_ROOT) for m in manifests),
        *manifests, PROJECT_ROOT,
    )
    output = args.output_prefix if args.output_prefix.is_absolute() else PROJECT_ROOT / args.output_prefix
    output.parent.mkdir(exist_ok=True, parents=True)
    output.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    output.with_suffix('.md').write_text(render(result), encoding='utf-8')
    print(f"Wrote {output.with_suffix('.md')} and .json ({result['n_matched_episodes']} matched episodes)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
