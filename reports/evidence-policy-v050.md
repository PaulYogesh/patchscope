# PatchScope v0.5 — patch-stage dependency evidence

Compared **4** matched episodes over **4** tasks.
Identical recorded exploration: **1/4**.

| Task | Same exploration | Baseline | Inventory | Static imports | Patch path (off → inventory → imports) |
|---|---|---|---|---|---|
| `mini-average-001` | NO | failed | failed | failed | `average_utils.py` → `average_utils.py` → `average_utils.py` |
| `mini-clamp-002` | NO | failed | failed | failed | `bounds_compat.py` → `bounds_compat.py` → `bounds_compat.py` |
| `mini-discount-004` | yes | verified | verified | verified | `checkout.py` → `checkout.py` → `checkout.py` |
| `mini-slug-003` | NO | failed | failed | failed | `slugify.py` → `slugify.py` → `None` |

## Interpretation

A matched exploration log is not proof of identical hidden state; inventory and imports prompts are not token-length matched. Only task-level descriptive comparisons are warranted.

Static import edges are unverified source relationships, not executable reachability evidence. This is a development-set diagnostic: do not claim generality or new benchmark significance.
