# PatchScope trajectory audit — smoke-v02

Audited 8 runs. Oracle localization is used for **post-hoc analysis only**; the oracle paths must not be provided to the model in native/BM25/placebo conditions.

## Evidence and exploration

| Condition | Runs | Oracle seeded | Oracle observed | Off-target reads | Repeat reads | Expanded seeded reads | Verified |
|---|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 2 | 2 | 2 | 6 | 0 | 0 | 2 |
| native | 2 | 0 | 2 | 6 | 0 | 0 | 2 |
| oracle | 2 | 2 | 2 | 6 | 0 | 0 | 2 |
| placebo | 2 | 0 | 2 | 4 | 2 | 0 | 2 |

## Repeat-trajectory diagnostics

4 task–condition groups had identical recorded decisions across all available repetitions.

- `mini-average-001` / `bm25`: 2 identical action-and-patch sequences
- `mini-average-001` / `native`: 2 identical action-and-patch sequences
- `mini-average-001` / `oracle`: 2 identical action-and-patch sequences
- `mini-average-001` / `placebo`: 2 identical action-and-patch sequences

**Interpretation:** identical decisions need not imply identical hidden reasoning. Equal outcomes or token totals alone do not establish identical actions. Off-target file reads are a proxy based on curated oracle labels, not proof that an action was unnecessary. These are diagnostic metrics, not claims of causal mediation.
