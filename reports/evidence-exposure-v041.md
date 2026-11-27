# PatchScope — evidence-exposure diagnostic

Offline descriptive analysis of recorded native-agent episodes. Paths and static imports are observable proxies, not model attention, causal mediation or proven runtime dependency.

## original: 4 tasks

Extra file observed by agent: **3/4**; first read: **3**; wrong-file patches: **3**; decoy-condition failures: **3**.

| Task | Neutral first read | Decoy first read | Decoy observed | True-file observed | Visible importer of true module | Decoy patched | Decoy verified |
|---|---|---|---|---|---|---|---|
| `mini-average-001` | `average_utils.py` | `average_utils.py` | yes | no | — | yes | no |
| `mini-clamp-002` | `bounds_compat.py` | `bounds_compat.py` | yes | yes | — | yes | no |
| `mini-discount-004` | `checkout.py` | `checkout.py` | no | yes | — | no | yes |
| `mini-slug-003` | `slugify.py` | `slugify.py` | yes | yes | — | yes | no |

Static import checks consider accessible non-test Python modules only. They do not prove that an import was executed or that a file caused the reported behavior.

## expanded: 8 tasks

Extra file observed by agent: **4/8**; first read: **0**; wrong-file patches: **0**; decoy-condition failures: **0**.

| Task | Neutral first read | Decoy first read | Decoy observed | True-file observed | Visible importer of true module | Decoy patched | Decoy verified |
|---|---|---|---|---|---|---|---|
| `backoff-ceiling-006` | `backoff.py` | `backoff.py` | no | yes | `service.py` | no | yes |
| `f1-harmonic-012` | `scores.py` | `scores.py` | no | yes | `service.py` | no | yes |
| `one-index-pages-008` | `pagination.py` | `pagination.py` | yes | yes | `service.py` | no | yes |
| `owner-access-009` | `constants.py` | `constants.py` | yes | yes | `service.py` | no | yes |
| `sensor-offset-010` | `calibration.py` | `calibration.py` | no | yes | `service.py` | no | yes |
| `stock-exact-007` | `allocation.py` | `allocation.py` | no | yes | `service.py` | no | yes |
| `tiered-billing-005` | `tax_math.py` | `tax_math.py` | yes | yes | `service.py` | no | yes |
| `window-inclusive-011` | `constants.py` | `constants.py` | yes | yes | `service.py` | no | yes |

Static import checks consider accessible non-test Python modules only. They do not prove that an import was executed or that a file caused the reported behavior.

## Interpretation gate

If a decoy was never observed, its source content cannot directly account for a later model decision through a displayed read or seed. Filename presence and file lists remain possible influences. If the decoy was observed and a wrong-locus patch followed, this is compatible with distraction, but it does not establish hidden reasoning.

Do not pool earlier hand-selected tasks with newer tasks without accounting for their different construction protocols.
