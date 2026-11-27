"""Run the matched three-way comparison for the eight new benchmark tasks."""
from scripts.compare_decoy_content import main

if __name__ == '__main__':
    raise SystemExit(main([
        '--clean-manifest', 'experiments/benchmark-clean-v040.json',
        '--neutral-manifest', 'experiments/benchmark-neutral-v040.json',
        '--decoy-manifest', 'experiments/benchmark-decoy-v040.json',
        '--output-prefix', 'reports/benchmark-content-v040',
    ]))
