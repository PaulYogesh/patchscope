"""Compare true-module evidence, decoy exposure and visible import references offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from patchscope.evidence_exposure import audit_content_exposure, render_exposure_markdown
from patchscope.experiment import PROJECT_ROOT, load_manifest

CASES = {
    'original': (
        'experiments/decoy_free_native_v031.json',
        'experiments/same_name_neutral_v032.json',
        'experiments/interference_smoke_v030.json',
    ),
    'expanded': (
        'experiments/benchmark-clean-v040.json',
        'experiments/benchmark-neutral-v040.json',
        'experiments/benchmark-decoy-v040.json',
    ),
}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=('original', 'expanded', 'both'), default='both')
    p.add_argument('--output', type=Path, default=Path('reports/evidence-exposure-v041'))
    args = p.parse_args(argv)
    audits = {}
    for case in (('original', 'expanded') if args.case == 'both' else (args.case,)):
        manifests = [load_manifest(PROJECT_ROOT / path) for path in CASES[case]]
        records = []
        for manifest in manifests:
            directory = PROJECT_ROOT / 'runs' / manifest['experiment_id']
            paths = sorted(directory.glob('*.json'))
            if not paths:
                p.error(f'Missing recorded runs for {case}: {directory}')
            records.append([json.loads(path.read_text(encoding='utf-8')) for path in paths])
        audits[case] = audit_content_exposure(*records, *manifests, PROJECT_ROOT)
    dest = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.with_suffix('.json').write_text(json.dumps(audits, indent=2)+'\n', encoding='utf-8')
    dest.with_suffix('.md').write_text(render_exposure_markdown(audits), encoding='utf-8')
    print(f'Wrote {dest.with_suffix(".md")} and {dest.with_suffix(".json")} (no model calls)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
