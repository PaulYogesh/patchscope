# PatchScope v0.6 — public execution-evidence pilot

Matched 2 native episodes across 2 fresh dynamic-dispatch tasks.

| Task | Off outcome | Public trace outcome | Off patch | Trace patch | Trace patch executed? | Same exploration? | Δ tokens |
|---|---|---|---|---|---|---|---:|
| `retry-dynamic-dispatch-014` | resolved | repair_failed_tests | `backoff_core.py` | `backoff_core.py` | yes | NO | 546 |
| `tax-dynamic-dispatch-013` | resolved | resolved | `tax_core.py` | `tax_core.py` | yes | NO | 9 |

Verified repairs: off **2/2**, public trace **1/2**.

## Limits

A public reproducer is an extra source of external execution evidence, not hidden oracle labels. It may make a small synthetic task easier by exposing its operative path. This preliminary study uses two authored synthetic tasks and is neither a held-out benchmark nor proof of improvement. The public reproducer is separate from pytest verification tests; the public script and verifier still share the same contract and need more independent tasks.

Trace execution is only file-level observed execution, not proof of fault, code causality, or complete program reachability. Model seeds do not enforce deterministic exploration. Prompt size differs across arms. Model-generated code executes only with explicit local opt-in; disposable directories are not security sandboxes.
