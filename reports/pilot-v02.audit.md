# PatchScope trajectory audit — pilot-v02

Audited 48 runs. Oracle localization is used for **post-hoc analysis only**; the oracle paths must not be provided to the model in native/BM25/placebo conditions.

## Evidence and exploration

| Condition | Runs | Oracle seeded | Oracle observed | Off-target reads | Repeat reads | Expanded seeded reads | Verified |
|---|---:|---:|---:|---:|---:|---:|---:|
| bm25 | 12 | 12 | 12 | 27 | 3 | 0 | 6 |
| native | 12 | 0 | 12 | 36 | 0 | 0 | 9 |
| oracle | 12 | 12 | 12 | 27 | 3 | 0 | 6 |
| placebo | 12 | 0 | 12 | 21 | 6 | 0 | 6 |

## Repeat-trajectory diagnostics

16 task–condition groups had identical recorded decisions across all available repetitions.

- `mini-average-001` / `bm25`: 3 identical action-and-patch sequences
- `mini-average-001` / `native`: 3 identical action-and-patch sequences
- `mini-average-001` / `oracle`: 3 identical action-and-patch sequences
- `mini-average-001` / `placebo`: 3 identical action-and-patch sequences
- `mini-clamp-002` / `bm25`: 3 identical action-and-patch sequences
- `mini-clamp-002` / `native`: 3 identical action-and-patch sequences
- `mini-clamp-002` / `oracle`: 3 identical action-and-patch sequences
- `mini-clamp-002` / `placebo`: 3 identical action-and-patch sequences
- `mini-discount-004` / `bm25`: 3 identical action-and-patch sequences
- `mini-discount-004` / `native`: 3 identical action-and-patch sequences
- `mini-discount-004` / `oracle`: 3 identical action-and-patch sequences
- `mini-discount-004` / `placebo`: 3 identical action-and-patch sequences
- `mini-slug-003` / `bm25`: 3 identical action-and-patch sequences
- `mini-slug-003` / `native`: 3 identical action-and-patch sequences
- `mini-slug-003` / `oracle`: 3 identical action-and-patch sequences
- `mini-slug-003` / `placebo`: 3 identical action-and-patch sequences

**Interpretation:** identical decisions need not imply identical hidden reasoning. Equal outcomes or token totals alone do not establish identical actions. Off-target file reads are a proxy based on curated oracle labels, not proof that an action was unnecessary. These are diagnostic metrics, not claims of causal mediation.
