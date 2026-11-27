# PatchScope — same-filename decoy-content control

8 paired native episodes; 8 distinct tasks.

All three repositories have byte-identical original source, issue and test files. The neutral and task-relevant decoy variants each add a Python file with the same **path**. Only that file's content differs, by at most 10% in byte length.

| Task | Clean | Same-name neutral | Task-relevant decoy | Clean patch | Neutral patch | Decoy patch | Δ decoy−neutral tokens |
|---|---|---|---|---|---|---|---:|
| `backoff-ceiling-006` | verified | verified | verified | `backoff.py` | `backoff.py` | `backoff.py` | +0 |
| `f1-harmonic-012` | verified | verified | verified | `scores.py` | `scores.py` | `scores.py` | +0 |
| `one-index-pages-008` | verified | verified | verified | `pagination.py` | `pagination.py` | `pagination.py` | +2467 |
| `owner-access-009` | verified | verified | verified | `policy.py` | `policy.py` | `policy.py` | +67 |
| `sensor-offset-010` | verified | verified | verified | `calibration.py` | `calibration.py` | `calibration.py` | +0 |
| `stock-exact-007` | verified | verified | verified | `allocation.py` | `allocation.py` | `allocation.py` | +0 |
| `tiered-billing-005` | verified | verified | verified | `tax_math.py` | `tax_math.py` | `tax_math.py` | +207 |
| `window-inclusive-011` | verified | verified | verified | `intervals.py` | `intervals.py` | `intervals.py` | -1369 |

## Descriptive summary

- Clean verified: **8/8**
- Same-name neutral verified: **8/8**
- Task-relevant decoy verified: **8/8**
- Success lost replacing neutral content with decoy content: **0**
- Success gained replacing neutral content with decoy content: **0**
- Patches to extra file: neutral **0**, decoy **0**
- Median extra tokens, neutral vs clean: **+182.0**
- Median extra tokens, decoy vs neutral: **+0.0**

## Scope and limitations

**Clean → neutral** changes repository composition (adds a source file and filename). **Neutral → decoy** keeps the added filename, file count, and all other bytes fixed, but changes source contents. This identifies a *controlled content-substitution contrast*, not a universal mechanism or the independent effect of a misleading injected seed.

This is a 8-task synthetic engineering control. Length matching is in source bytes, not model tokens. Model seeds and configurations are matched, but temperature zero does not guarantee fully deterministic inference. Do not infer population effects, hidden reasoning, or statistical significance. Review failed-test traces before claiming the agent relied on any specific excerpt.

## Exact neutral/decoy file parity

| Task | Shared extra filename | Neutral bytes | Decoy bytes |
|---|---|---:|---:|
| `backoff-ceiling-006` | `retry_compat.py` | 116 | 116 |
| `f1-harmonic-012` | `scores_compat.py` | 95 | 95 |
| `one-index-pages-008` | `pagination_compat.py` | 74 | 74 |
| `owner-access-009` | `policy_compat.py` | 113 | 113 |
| `sensor-offset-010` | `calibration_compat.py` | 93 | 93 |
| `stock-exact-007` | `stock_compat.py` | 94 | 94 |
| `tiered-billing-005` | `tax_compat.py` | 97 | 97 |
| `window-inclusive-011` | `window_compat.py` | 96 | 96 |
