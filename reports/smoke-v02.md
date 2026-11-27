# PatchScope v0.2 — smoke-v02

## Protocol

Four context conditions: native (no seed), BM25, curated unrelated placebo, and oracle-localized source. Conditions were scheduled in deterministic, randomized order within (task, repetition) blocks and assigned the same model seed within each block.

Only verified passing tests *after* a failing baseline count as repairs. A model patch is not a verified repair.

## Sample: 1 tasks, 8 recorded runs

## Outcome summary

| Condition | Runs | Evaluated | Verified | Repair rate | Median tokens | Median tools | Repeated reads | Protocol errors | Unverified |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 2 | 2 | 2 | 1.000 | 3137 | 4.0 | 0.0 | 0 | 0 |
| native | 2 | 2 | 2 | 1.000 | 2889 | 5.0 | 0.0 | 0 | 0 |
| oracle | 2 | 2 | 2 | 1.000 | 3137 | 4.0 | 0.0 | 0 | 0 |
| placebo | 2 | 2 | 2 | 1.000 | 4544 | 4.0 | 1.0 | 0 | 0 |

## Paired comparisons

| Comparison | Matched pairs | Risk difference | Task-cluster 95% CI | A-only / B-only | Exact McNemar p | Median Δ tokens |
|---|---:|---:|---|---:|---:|---:|
| bm25 - native | 2 | 0.000 | — | 0 / 0 | 1.000 | 248 |
| bm25 - placebo | 2 | 0.000 | — | 0 / 0 | 1.000 | -1407 |
| oracle - native | 2 | 0.000 | — | 0 / 0 | 1.000 | 248 |
| oracle - bm25 | 2 | 0.000 | — | 0 / 0 | 1.000 | 0 |
| oracle - placebo | 2 | 0.000 | — | 0 / 0 | 1.000 | -1407 |

Confidence intervals resample **tasks**, not individual repetitions. Intervals are omitted when fewer than two tasks are paired. The small pilot is for instrumentation and effect estimation, not for asserting a statistically established performance advantage. Runs with verification explicitly disabled are excluded from the repair-rate denominator and paired outcomes; model/protocol failures are counted as failures.

## Tool and runtime behavior

The raw JSON records contain the per-call prompt/completion usage, full visible transcript, validated tools, repeated reads, and test events.

- **bm25:** median retrieval 0.784 ms; median wall time 10.396 s.
- **native:** median retrieval 0.003 ms; median wall time 10.178 s.
- **oracle:** median retrieval 0.249 ms; median wall time 10.335 s.
- **placebo:** median retrieval 1.419 ms; median wall time 10.055 s.

## Reproducibility provenance

- Model: `qwen3.5:9b`
- Model digest: `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`
- Ollama: `0.40.5`
- Git commit: `9b95076b8989ff372100354d98376cf2502017c1`
- Manifest SHA256: `1acca8d9b0a60899fadaa326b70e88fd650a546ea45ed154695d395980113511`
- Prompt version: `patchscope-agent-v02-001`
- Tool schema SHA256: `a1e5c42ff0e9c070aa0cc69c38ff1b074a881deb939e28e5ddd50ecf29fc20fe`

## Methodology

```mermaid
flowchart LR
  A[Task and repetition] --> B[Randomized context intervention]
  B --> C[Same agent and allowed read tools]
  C --> D[Patch proposal]
  D --> E[Disposable trusted fixture copy]
  E --> F[Baseline and patched pytest]
  F --> G[Structured logs and paired statistics]
```

## Limitations

- Context conditions are not a substitute for a larger, curated sample of real software defects.
- Oracle localization is privileged evaluator data and measures available headroom.
- Curated placebo code is only approximately length matched; see per-run length-gap metadata.
- A temporary copy does not sandbox test execution; execution requires explicit local opt-in.
- Temperature zero and a model seed do not guarantee perfectly repeatable inference.
- Missing or unverified outcomes must not be interpreted as verified repairs.
