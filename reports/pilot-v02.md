# PatchScope v0.2 — pilot-v02

## Protocol

Four context conditions: native (no seed), BM25, curated unrelated placebo, and oracle-localized source. Conditions were scheduled in deterministic, randomized order within (task, repetition) blocks and assigned the same model seed within each block.

Only verified passing tests *after* a failing baseline count as repairs. A model patch is not a verified repair.

## Sample: 4 tasks, 48 recorded runs

## Outcome summary

| Condition | Runs | Evaluated | Verified | Repair rate | Median tokens | Median tools | Repeated reads | Protocol errors | Unverified |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 12 | 12 | 6 | 0.500 | 3268 | 4.0 | 0.0 | 0 | 0 |
| native | 12 | 12 | 9 | 0.750 | 2894 | 5.0 | 0.0 | 0 | 0 |
| oracle | 12 | 12 | 6 | 0.500 | 3268 | 4.0 | 0.0 | 0 | 0 |
| placebo | 12 | 12 | 6 | 0.500 | 3456 | 4.0 | 0.5 | 0 | 0 |

## Paired comparisons

| Comparison | Matched pairs | Risk difference | Task-cluster 95% CI | A-only / B-only | Exact McNemar p | Median Δ tokens |
|---|---:|---:|---|---:|---:|---:|
| bm25 - native | 12 | -0.250 | [-0.750, 0.000] | 0 / 3 | — | 312 |
| bm25 - placebo | 12 | 0.000 | [0.000, 0.000] | 0 / 0 | — | -95 |
| oracle - native | 12 | -0.250 | [-0.750, 0.000] | 0 / 3 | — | 312 |
| oracle - bm25 | 12 | 0.000 | [0.000, 0.000] | 0 / 0 | — | 0 |
| oracle - placebo | 12 | 0.000 | [0.000, 0.000] | 0 / 0 | — | -95 |

Confidence intervals resample **tasks**, not individual repetitions. Intervals are omitted when fewer than two tasks are paired. The small pilot is for instrumentation and effect estimation, not for asserting a statistically established performance advantage. Runs with verification explicitly disabled are excluded from the repair-rate denominator and paired outcomes; model/protocol failures are counted as failures. **McNemar p-values are omitted when matched pairs include repeated observations from the same task** because those pairs are not independent. Discordance counts remain descriptive.

## Tool and runtime behavior

The raw JSON records contain the per-call prompt/completion usage, full visible transcript, validated tools, repeated reads, and test events.

- **bm25:** median retrieval 0.732 ms; median wall time 13.823 s.
- **native:** median retrieval 0.002 ms; median wall time 10.264 s.
- **oracle:** median retrieval 0.207 ms; median wall time 13.771 s.
- **placebo:** median retrieval 1.187 ms; median wall time 10.645 s.

## Reproducibility provenance

- Model: `qwen3.5:9b`
- Model digest: `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`
- Ollama: `0.40.5`
- Git commit: `9b95076b8989ff372100354d98376cf2502017c1`
- Working tree dirty: `True`
- Source and fixture SHA256: `adc272071daa30b0db3648b1ba648e391251dcc9bf537ec31278b0509c680a11`
- Manifest SHA256: `830c9cbf2f8d9e206a7aef2e1fea34db5c2b211e63e923523cb8a5fe497473c4`
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
