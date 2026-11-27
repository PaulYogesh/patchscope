# PatchScope v0.2.0-alpha — Local experimental harness

## New

- Four initial-context interventions: native, BM25, placebo, oracle.
- Deterministic task/repetition blocking, shared generation seeds, randomized condition order.
- Strict native tool protocol for primary experiments, marked text fallback for compatibility runs.
- Validated task JSON manifests, optional trusted-fixture verification opt-in, run-by-run JSON logs.
- Paired exploratory statistics and neutral Markdown reporting.
- Three additional executable synthetic fixtures with known reference corrections.
- CPU-only unit tests and prospective GitHub Actions configuration.

## Compatibility

Original v0.1 retrieval, repair, smoke scripts and development report are retained.

## Not completed

Real Qwen3.5 8-run and 48-run pilot results; twelve-task/144-run study; container isolation for generated code; scientific validation beyond synthetic smoke fixtures.

## Security

Temporary directories are **not sandboxes**. The batch experiment CLI requires explicit `--allow-trusted-execution` to execute a model-generated patch through pytest, and only for tasks marked `trusted_execution: true`. Never enable this for untrusted repositories; use container isolation for that work.
