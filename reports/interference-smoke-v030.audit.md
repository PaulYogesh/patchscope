# PatchScope trajectory audit — interference-smoke-v030

Audited 20 runs. Oracle localization is used for **post-hoc analysis only**; the oracle paths must not be provided to the model in native/BM25/placebo/misleading conditions.

## Evidence and exploration

| Condition | Runs | Oracle seeded | Wrong-locus seeded | Oracle observed | Wrong-locus patches | Off-target reads | Repeat reads | Expanded seeded reads | Verified |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 4 | 1 | 2 | 2 | 1 | 10 | 2 | 0 | 2 |
| misleading | 4 | 0 | 4 | 2 | 3 | 9 | 2 | 0 | 1 |
| native | 4 | 0 | 0 | 3 | 3 | 7 | 0 | 0 | 1 |
| oracle | 4 | 4 | 0 | 4 | 0 | 7 | 4 | 0 | 4 |
| placebo | 4 | 0 | 0 | 3 | 0 | 5 | 1 | 0 | 3 |

## Repeat-trajectory diagnostics

0 task–condition groups had identical recorded decisions across all available repetitions.

No repeated group was perfectly identical across all recorded repetitions (or no group had multiple runs).

**Interpretation:** identical decisions need not imply identical hidden reasoning. Equal outcomes or token totals alone do not establish identical actions. Off-target file reads are a proxy based on curated oracle labels, not proof that an action was unnecessary. These are diagnostic metrics, not claims of causal mediation.
