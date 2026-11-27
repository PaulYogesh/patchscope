# PatchScope v0.5.1 — frozen-exploration proposal comparison

Compared 4 matched task episodes; no exploration rerun.
All three policies receive exactly the same recorded source excerpts. Only proposal-stage evidence hints differ.

| Task | Static edges | Off | Inventory | Imports | Patch path (off / inventory / imports) |
|---|---:|---|---|---|---|
| `mini-average-001` | 0 | repair_failed_tests | repair_failed_tests | repair_failed_tests | `average_utils.py` / `average_utils.py` / `average_utils.py` |
| `mini-clamp-002` | 0 | repair_failed_tests | repair_failed_tests | repair_failed_tests | `bounds_compat.py` / `bounds_compat.py` / `bounds_compat.py` |
| `mini-discount-004` | 0 | verified | verified | verified | `checkout.py` / `checkout.py` / `checkout.py` |
| `mini-slug-003` | 0 | repair_failed_tests | repair_failed_tests | error | `slugify.py` / `slugify.py` / `None` |
- **off:** 1/4 verified
- **inventory:** 1/4 verified
- **imports:** 1/4 verified

## Interpretation limits

This is a **proposal-stage** comparison on previously selected source excerpts, not a whole-agent repair evaluation. All frozen excerpts, seeds and model digests are checked for equality across arms. Prompt sizes and wording differ. Randomness can remain despite fixed seeds.

The original four tasks contain no explicit static source-import edges; this treatment should not be described as a dependency-aware solution if the report confirms zero edges. No gold-path labels are passed to the model.
