"""Compare new v0.6 native runs with and without public reproduction evidence."""
import json
from patchscope.operative_compare import compare_operative, render_operative
from patchscope.experiment import PROJECT_ROOT


def main():
    result = compare_operative(PROJECT_ROOT)
    target = PROJECT_ROOT / 'reports' / 'operative-evidence-v060'
    target.parent.mkdir(exist_ok=True)
    target.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
    target.with_suffix('.md').write_text(render_operative(result))
    print(f'Wrote {target}.md and .json ({result["n_matched"]} matched tasks)')

if __name__ == '__main__':
    main()
