# PatchScope v0.6-alpha — public execution evidence (prototype)

## Why this exists

The v0.5.1 frozen-exploration replay found **no improvement** from source-file inventory or static imports on the four original synthetic development tasks (1/4 verified per arm). All four had zero explicit source-to-source import edges. We freeze that negative result instead of tuning the prompt repeatedly.

## New experiment

- `patchscope/operative_trace.py`: opt-in execution trace of a **separate public bug reproducer** on a disposable clone; records executed repository Python paths and an error type (not private tests, gold labels, or full stack contents). The trace is advisory evidence, **not a determination of blame**.
- `operative_trace_policy` is `off` by default for all historical manifests; `public_reproducer` adds the trace **before exploration** so the agent can read an implicated but previously unseen module. The proposal still edits only observed code.
- New synthetic dynamic-dispatch defects: `tax-dynamic-dispatch-013` and `retry-dynamic-dispatch-014`, each with a public reproducer outside its repository and independent pytest checks.
- Two new manifests (`operative-off-v060`, `operative-trace-v060`) preserve matching model seeds, tasks, conditions and budgets. They have distinct experiment IDs and records.
- `scripts.compare_operative_v060`: strict matched comparison of patch locus, verified repairs, original exploration fingerprints, token costs, and model/source digests.
- Reproducer scripts are now included in `source_tree_sha256` provenance.

## Scope and major caveats

1. This is a small **engineering feasibility pilot**, **not** evidence of a scientific improvement. Two new synthetic tasks do not estimate a population effect.
2. Public reproducers can make an issue easier by revealing executed modules. They are external task information; this changes the agent's information budget. Runtime execution does not prove a file is faulty.
3. In real benchmarks, construct genuinely public reproductions **independently** from held-out tests, register them *before* running models, and evaluate on unseen tasks. Reproducer and current synthetic hidden test are separate files but share the same bug contract.
4. Trace execution runs Python code and is **not security sandboxed**, even though the repository is copied. The CLI requires `--allow-trusted-execution`. Use only audited, local toy fixtures. Never run arbitrary third-party repos this way.
5. Do not combine these new results with prior v0.5.1 replay outcomes: the task construction and evidence protocol differ.
