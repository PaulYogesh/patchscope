# PatchScope v0.2 — interference-smoke-v030

## Protocol

Recorded context conditions: bm25, misleading, native, oracle, placebo. Interventions were assigned deterministic randomized order within (task, repetition) blocks, with matched model seeds. Misleading, when present, seeds genuine task-relevant code from a curated wrong-locus repository file, not fabricated source content.

Only verified passing tests *after* a failing baseline count as repairs. A model patch is not a verified repair.

## Sample: 4 tasks, 20 recorded runs

## Outcome summary

| Condition | Runs | Evaluated | Verified | Repair rate | Median tokens | Median tools | Repeated reads | Proposal rejects | Recovered | Protocol errors | Unverified |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 4 | 4 | 2 | 0.500 | 4494 | 4.0 | 0.5 | 2 | 0 | 0 | 0 |
| misleading | 4 | 4 | 1 | 0.250 | 3688 | 4.0 | 0.5 | 0 | 0 | 0 | 0 |
| native | 4 | 4 | 1 | 0.250 | 3408 | 3.0 | 0.0 | 0 | 0 | 0 | 0 |
| oracle | 4 | 4 | 4 | 1.000 | 3892 | 3.5 | 1.0 | 0 | 0 | 0 | 0 |
| placebo | 4 | 4 | 3 | 0.750 | 4074 | 2.0 | 0.0 | 2 | 0 | 0 | 0 |

## Paired comparisons

| Comparison | Matched pairs | Risk difference | Task-cluster 95% CI | A-only / B-only | Exact McNemar p | Median Δ tokens |
|---|---:|---:|---|---:|---:|---:|
| bm25 - native | 4 | 0.250 | [0.000, 0.750] | 1 / 0 | 1.000 | 1282 |
| bm25 - placebo | 4 | -0.250 | [-0.750, 0.000] | 0 / 1 | 1.000 | 539 |
| oracle - native | 4 | 0.750 | [0.250, 1.000] | 3 / 0 | 0.250 | 399 |
| oracle - bm25 | 4 | 0.500 | [0.000, 1.000] | 2 / 0 | 0.500 | -430 |
| oracle - placebo | 4 | 0.250 | [0.000, 0.750] | 1 / 0 | 1.000 | -344 |
| misleading - native | 4 | 0.000 | [0.000, 0.000] | 0 / 0 | 1.000 | 826 |
| misleading - placebo | 4 | -0.500 | [-1.000, 0.000] | 0 / 2 | 0.500 | -320 |
| misleading - oracle | 4 | -0.750 | [-1.000, -0.250] | 0 / 3 | 0.250 | 198 |

Confidence intervals resample **tasks**, not individual repetitions. Intervals are omitted when fewer than two tasks are paired. The small pilot is for instrumentation and effect estimation, not for asserting a statistically established performance advantage. Runs with verification explicitly disabled are excluded from the repair-rate denominator and paired outcomes; model/protocol failures are counted as failures. **McNemar p-values are omitted when matched pairs include repeated observations from the same task** because those pairs are not independent. Discordance counts remain descriptive.

## Tool and runtime behavior

The raw JSON records contain the per-call prompt/completion usage, full visible transcript, validated tools, repeated reads, and test events.

- **bm25:** median retrieval 0.816 ms; median wall time 19.575 s.
- **misleading:** median retrieval 1.025 ms; median wall time 17.950 s.
- **native:** median retrieval 0.003 ms; median wall time 11.622 s.
- **oracle:** median retrieval 0.237 ms; median wall time 17.557 s.
- **placebo:** median retrieval 1.281 ms; median wall time 12.668 s.

## Reproducibility provenance

- Model: `qwen3.5:9b`
- Model digest: `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`
- Ollama: `0.40.5`
- Git commit: `9b95076b8989ff372100354d98376cf2502017c1`
- Working tree dirty: `True`
- Source and fixture SHA256: `2c37befd6ddc3098844e18ab6bf781d84d136fb2a6b38dfa1b6210efb1e76757`
- Manifest SHA256: `15e9c44d0f1d5466855a332a3ed00d410f74d2a35d832f7408cccf570cc51b02`
- Prompt version: `patchscope-agent-v023-001`
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
- Curated placebo and misleading code are only approximately length matched; see per-run length-gap metadata.
- Misleading decoys are deliberately synthetic wrong-locus implementations; evaluate on more natural repositories before generalizing.
- A temporary copy does not sandbox test execution; execution requires explicit local opt-in.
- Temperature zero and a model seed do not guarantee perfectly repeatable inference.
- Missing or unverified outcomes must not be interpreted as verified repairs.
