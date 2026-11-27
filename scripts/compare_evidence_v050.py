"""Compare historical native baseline to inventory/import-map patch-stage runs."""
from __future__ import annotations

import argparse
import json

from patchscope.evidence_policy_compare import compare_policies, load_native_records, render_comparison
from patchscope.experiment import PROJECT_ROOT


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',default='interference-smoke-v030')
    parser.add_argument('--inventory',default='evidence-inventory-v050')
    parser.add_argument('--imports',default='evidence-imports-v050')
    args=parser.parse_args(argv)
    ids={'baseline':args.baseline,'inventory':args.inventory,'imports':args.imports}
    arms={name:load_native_records(PROJECT_ROOT, id) for name,id in ids.items()}
    report=compare_policies(arms)
    destination=PROJECT_ROOT/'reports'/'evidence-policy-v050'
    destination.parent.mkdir(exist_ok=True)
    destination.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    destination.with_suffix('.md').write_text(render_comparison(report))
    print(f'Wrote {destination}.md and .json ({report["n_pairs"]} matched episodes)')

if __name__=='__main__':
    main()
