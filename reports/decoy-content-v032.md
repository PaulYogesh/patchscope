# PatchScope — same-filename decoy-content control

4 paired native episodes; 4 distinct tasks.

All three repositories have byte-identical original source, issue and test files. The neutral and task-relevant decoy variants each add a Python file with the same **path**. Only that file's content differs, by at most 10% in byte length.

| Task | Clean | Same-name neutral | Task-relevant decoy | Clean patch | Neutral patch | Decoy patch | Δ decoy−neutral tokens |
|---|---|---|---|---|---|---|---:|
| `mini-average-001` | verified | verified | repair_failed_tests | `calculator.py` | `calculator.py` | `average_utils.py` | -500 |
| `mini-clamp-002` | verified | verified | repair_failed_tests | `limits.py` | `limits.py` | `bounds_compat.py` | -12 |
| `mini-discount-004` | verified | verified | verified | `checkout.py` | `checkout.py` | `checkout.py` | +43 |
| `mini-slug-003` | verified | verified | repair_failed_tests | `text_ops.py` | `text_ops.py` | `slugify.py` | -1510 |

## Descriptive summary

- Clean verified: **4/4**
- Same-name neutral verified: **4/4**
- Task-relevant decoy verified: **1/4**
- Success lost replacing neutral content with decoy content: **3**
- Success gained replacing neutral content with decoy content: **0**
- Patches to extra file: neutral **0**, decoy **3**
- Median extra tokens, neutral vs clean: **+918.5**
- Median extra tokens, decoy vs neutral: **-256.0**

## Scope and limitations

**Clean → neutral** changes repository composition (adds a source file and filename). **Neutral → decoy** keeps the added filename, file count, and all other bytes fixed, but changes source contents. This identifies a *controlled content-substitution contrast*, not a universal mechanism or the independent effect of a misleading injected seed.

This is a four-task synthetic engineering control. Length matching is in source bytes, not model tokens. Model seeds and configurations are matched, but temperature zero does not guarantee fully deterministic inference. Do not infer population effects, hidden reasoning, or statistical significance. Review failed-test traces before claiming the agent relied on any specific excerpt.

## Exact neutral/decoy file parity

| Task | Shared extra filename | Neutral bytes | Decoy bytes |
|---|---|---:|---:|
| `mini-average-001` | `average_utils.py` | 197 | 197 |
| `mini-clamp-002` | `bounds_compat.py` | 210 | 210 |
| `mini-discount-004` | `pricing_compat.py` | 261 | 259 |
| `mini-slug-003` | `slugify.py` | 123 | 120 |
