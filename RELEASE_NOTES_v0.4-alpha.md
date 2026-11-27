# PatchScope v0.4-alpha — independent synthetic task-set expansion

## Added

- Eight **new** cross-module synthetic repair tasks in distinct application
  families: billing, retry, stock allocation, pagination, authorization,
  sensor calibration, temporal windows, and scoring.
- For each task, full clean, neutral-extra-file, and task-relevant decoy-extra-
  file fixture variants (24 fixture repositories).
- Three frozen v0.4 manifests with identical native-agent model seeds and
  generation budgets; 24 native episodes constitute the primary control.
- Regression tests for baseline failure, reference repair success, decoy-only
  edit failure, shared-file equality, same-filename/length parity, and decoy
  import isolation.
- Reusable `--output-prefix` option for the existing three-way comparison CLI;
  new shortcut `scripts.compare_benchmark_v040`.

## Preserved

- All v0.1–v0.3.2 fixtures, experiment IDs, logs and agent behavior.
- No external model calls and no fabricated benchmark outcomes in this archive.

## Limitations

- These are curated synthetic single-locus bugs behind cross-module APIs,
  not real-world multihunk repairs or a statistically representative corpus.
- Decoys are added files rather than naturally occurring repository ambiguity.
- Equal byte lengths do not imply equal token counts or equivalent semantics.
- v0.4 outcomes are unknown until the user runs Qwen on the supplied fixtures.
